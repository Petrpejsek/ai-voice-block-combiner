from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import json
from datetime import datetime, timezone
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
import numpy as np
import threading
import requests  # For Google TTS REST API calls
import base64    # For decoding audioContent
import time      # For token caching

# Farm-proof: load backend/.env manually (so API keys saved via UI work),
# but never crash if the file is missing or unreadable (e.g. restricted env).
try:
    from dotenv import load_dotenv
    _dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(_dotenv_path):
        load_dotenv(_dotenv_path, override=False)
except Exception as e:
    print(f"⚠️  app: load_dotenv skipped: {e}")

# MoviePy importy pro video generování
try:
    from moviepy import ImageClip, concatenate_videoclips, VideoClip, AudioFileClip, CompositeVideoClip, concatenate_audioclips
    MOVIEPY_AVAILABLE = True
    print("✅ MoviePy knihovny úspěšně načteny")
except Exception as e:
    print(f"❌ Chyba při importu MoviePy: {e}")
    MOVIEPY_AVAILABLE = False

# Import DALL-E funkcí
from gpt_utils import generate_dalle_images, download_image_from_url, call_openai

# Script pipeline (Research -> Narrative -> Validation -> Composer)
from project_store import ProjectStore
from script_pipeline import ScriptPipelineService
from settings_store import SettingsStore
from visual_assistant import run_visual_assistant
from music_store import (
    load_music_manifest,
    add_music_files,
    update_music_track,
    music_dir_for_episode,
)
from global_music_store import (
    load_global_music_manifest,
    add_global_music_files,
    update_global_music_track,
    delete_global_music_track,
    select_music_auto,
    get_music_file_path,
    global_music_dir,
)

app = Flask(__name__)
CORS(app)

# Farm-proof upload size guard (applies to all uploads)
# - Music: up to ~100MB
# - Video backgrounds already allow 100MB
app.config["MAX_CONTENT_LENGTH"] = 110 * 1024 * 1024  # 110MB


@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(e):
    return jsonify({"success": False, "error": "Soubor je příliš velký (limit 110MB)"}), 413


@app.route('/health', methods=['GET'])
def health_root():
    """Simple healthcheck alias (user-friendly)."""
    return jsonify({"status": "OK", "service": "backend", "port": int(os.environ.get("PORT", 50000))})


@app.route('/', methods=['GET'])
def root_index():
    return jsonify({"status": "OK", "service": "podcasts-backend", "hint": "Use /api/health and /api/* endpoints"})

# Složky pro soubory
# BASE_DIR should point to /Users/petrliesner/podcasts (workspace root)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'output')
IMAGES_FOLDER = os.path.join(BASE_DIR, 'images')
BACKGROUNDS_FOLDER = os.path.join(BASE_DIR, 'uploads', 'backgrounds')
VIDEO_BACKGROUNDS_FOLDER = os.path.join(BASE_DIR, 'uploads', 'video_backgrounds')
PROJECTS_FOLDER = os.path.join(BASE_DIR, 'projects')
CONFIG_FOLDER = os.path.join(BASE_DIR, 'config')

# Vytvoř složky pokud neexistují
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(IMAGES_FOLDER, exist_ok=True)
os.makedirs(BACKGROUNDS_FOLDER, exist_ok=True)
os.makedirs(VIDEO_BACKGROUNDS_FOLDER, exist_ok=True)
os.makedirs(PROJECTS_FOLDER, exist_ok=True)
os.makedirs(CONFIG_FOLDER, exist_ok=True)

print("🎬 FINAL FIXED Ken Burns Backend")
print(f"📂 Images folder: {IMAGES_FOLDER}")
print(f"📁 Output folder: {OUTPUT_FOLDER}")

# Script pipeline singletons
project_store = ProjectStore(PROJECTS_FOLDER)
script_pipeline_service = ScriptPipelineService(project_store)
settings_store = SettingsStore(BASE_DIR, os.path.dirname(os.path.abspath(__file__)))

def create_ken_burns_effect(image_path, duration, target_width, target_height, effect_type=0):
    """
    Vytvoří skutečný Ken Burns efekt s animací
    effect_type: 0=zoom_in, 1=zoom_out, 2=pan_left, 3=pan_right
    """
    if not MOVIEPY_AVAILABLE:
        raise Exception("MoviePy není dostupné")
    
    try:
        print(f"🎬 Vytvářím animovaný Ken Burns efekt pro {image_path}, duration={duration}s, efekt={effect_type}")
        
        # Vytvoř základní ImageClip
        base_clip = ImageClip(image_path)
        
        # Získej původní rozměry obrázku
        img_width, img_height = base_clip.size
        print(f"📐 Původní rozměry: {img_width}x{img_height}")
        
        # OPTIMALIZACE: Předřež obrázek na rozumnou velikost pro Ken Burns
        # Maximální velikost 2x target rozměry pro Ken Burns efekt
        max_work_width = target_width * 2
        max_work_height = target_height * 2
        
        if img_width > max_work_width or img_height > max_work_height:
            # Změň velikost obrázku před Ken Burns pro rychlost
            base_clip = base_clip.resized((max_work_width, max_work_height))
            print(f"🔧 OPTIMALIZACE: Obrázek zmenšen na {max_work_width}x{max_work_height} pro rychlost")
        
        # Spočítej poměr pro Ken Burns efekt
        scale_factor = 1.3  # Kolik zvětšit/zmenšit
        
        def make_frame(t):
            """Vytvoří snímek pro čas t"""
            # Normalizuj čas (0 až 1)
            progress = t / duration
            
            # PLYNULÉ EASING - pro odstranění "cukání"
            # Použij smooth S-křivku místo lineární interpolace
            progress = progress * progress * (3.0 - 2.0 * progress)  # Smoothstep funkce
            
            if effect_type == 0:  # Zoom In
                # Začni větší a postupně zmenšuj
                current_scale = scale_factor - (scale_factor - 1.0) * progress
                new_width = int(target_width * current_scale)
                new_height = int(target_height * current_scale)
                x_center = (new_width - target_width) // 2
                y_center = (new_height - target_height) // 2
                
            elif effect_type == 1:  # Zoom Out  
                # Začni menší a postupně zvětšuj
                current_scale = 1.0 + (scale_factor - 1.0) * progress
                new_width = int(target_width * current_scale)
                new_height = int(target_height * current_scale)
                x_center = (new_width - target_width) // 2
                y_center = (new_height - target_height) // 2
                
            elif effect_type == 2:  # Pan Left
                # Posouvej zleva doprava
                new_width = int(target_width * scale_factor)
                new_height = int(target_height * scale_factor)
                x_center = int((new_width - target_width) * progress)
                y_center = (new_height - target_height) // 2
                
            else:  # Pan Right (effect_type == 3)
                # Posouvej zprava doleva
                new_width = int(target_width * scale_factor)
                new_height = int(target_height * scale_factor)
                x_center = int((new_width - target_width) * (1 - progress))
                y_center = (new_height - target_height) // 2
            
            # Změň velikost obrázku
            try:
                resized_clip = base_clip.resized((new_width, new_height))
            except:
                try:
                    resized_clip = base_clip.resized(newsize=(new_width, new_height))
                except:
                    # Fallback - použij původní velikost
                    resized_clip = base_clip.resized((target_width, target_height))
                    return resized_clip.get_frame(0)
            
            # Získej snímek a ořízni ho
            frame = resized_clip.get_frame(0)
            
            # Ořízni na požadovanou velikost
            if x_center < 0:
                x_center = 0
            if y_center < 0:
                y_center = 0
            if x_center + target_width > new_width:
                x_center = new_width - target_width
            if y_center + target_height > new_height:
                y_center = new_height - target_height
                
            cropped_frame = frame[y_center:y_center+target_height, x_center:x_center+target_width]
            
            return cropped_frame
        
        # Vytvoř animovaný klip
        animated_clip = VideoClip(make_frame, duration=duration)
        
        print(f"✅ Ken Burns efekt úspěšně vytvořen: {duration}s")
        return animated_clip
        
    except Exception as e:
        print(f"❌ Chyba při vytváření Ken Burns efektu: {e}")
        # Fallback - pouze statický obrázek
        try:
            print(f"⚠️ Fallback na statický obrázek")
            clip = ImageClip(image_path, duration=duration)
            try:
                clip = clip.resized((target_width, target_height))
            except:
                pass
            return clip
        except Exception as fallback_error:
            print(f"❌ I fallback selhal: {fallback_error}")
            raise Exception(f"Nelze vytvořit ani základní klip: {fallback_error}")

def create_fast_ken_burns_effect(image_path, duration, target_width, target_height, effect_type=0):
    """
    ⚡ SUPER RYCHLÁ verze Ken Burns efektů - skutečně optimalizováno!
    """
    if not MOVIEPY_AVAILABLE:
        raise Exception("MoviePy není dostupné")
    
    try:
        print(f"⚡ Vytvářím SUPER RYCHLÝ Ken Burns efekt pro {image_path}, duration={duration}s, efekt={effect_type}")
        
        # SUPER NÍZKÉ rozlišení pro rychlost - 360p max
        work_width = min(target_width, 360)  # Max 360p pro super rychlost
        work_height = int(work_width * target_height / target_width)
        
        print(f"🔧 RYCHLÁ OPTIMALIZACE: Pracovní rozlišení {work_width}x{work_height}")
        
        # Načti obrázek jednou a předzpracuj ho
        base_clip = ImageClip(image_path)
        
        # PŘEDEM zmenši na pracovní rozlišení s rezervou pro efekty
        work_scale = 1.3  # Menší rezerva pro rychlost
        pre_width = int(work_width * work_scale)
        pre_height = int(work_height * work_scale)
        
        # Předem připrav obrázek v správné velikosti
        prepared_clip = base_clip.resized((pre_width, pre_height))
        prepared_frame = prepared_clip.get_frame(0)
        
        print(f"🚀 PŘEDPŘIPRAVENÝ frame: {pre_width}x{pre_height}")
        
        # STATICKÉ pozice místo animace - rychlejší
        def make_fast_frame(t):
            """Rychlá verze s méně výpočty"""
            # Normalizuj čas (0 až 1)
            progress = t / duration
            
            # Jednoduchý smoothing - levnější než smoothstep
            progress = 0.5 * (1 - np.cos(np.pi * progress))
            
            if effect_type == 0:  # Zoom In
                # Start větší, end menší
                scale = work_scale - (work_scale - 1.0) * progress
                crop_w = int(work_width * scale)
                crop_h = int(work_height * scale)
                x_start = (pre_width - crop_w) // 2
                y_start = (pre_height - crop_h) // 2
                
            elif effect_type == 1:  # Zoom Out
                # Start menší, end větší
                scale = 1.0 + (work_scale - 1.0) * progress
                crop_w = int(work_width * scale)
                crop_h = int(work_height * scale)
                x_start = (pre_width - crop_w) // 2
                y_start = (pre_height - crop_h) // 2
                
            elif effect_type == 2:  # Pan Left (zleva doprava)
                crop_w = work_width
                crop_h = work_height
                x_start = int((pre_width - crop_w) * progress)
                y_start = (pre_height - crop_h) // 2
                
            else:  # Pan Right (zprava doleva)
                crop_w = work_width
                crop_h = work_height
                x_start = int((pre_width - crop_w) * (1 - progress))
                y_start = (pre_height - crop_h) // 2
            
            # Zajisti že nepřekročíme hranice
            x_start = max(0, min(x_start, pre_width - crop_w))
            y_start = max(0, min(y_start, pre_height - crop_h))
            x_end = min(x_start + crop_w, pre_width)
            y_end = min(y_start + crop_h, pre_height)
            
            # Vyřízni region
            cropped = prepared_frame[y_start:y_end, x_start:x_end]
            
            # Zajisti správnou velikost (resize když je potřeba)
            if cropped.shape[:2] != (work_height, work_width):
                from moviepy.video.fx.Resize import resize
                temp_clip = ImageClip(cropped, duration=0.1)
                resized_clip = temp_clip.resized((work_width, work_height))
                cropped = resized_clip.get_frame(0)
                temp_clip.close()
                resized_clip.close()
            
            return cropped
        
        # Vytvoř rychlý animovaný klip
        fast_clip = VideoClip(make_fast_frame, duration=duration)
        
        # Upscale na finální rozlišení pouze jednou na konci
        if work_width != target_width or work_height != target_height:
            final_clip = fast_clip.resized((target_width, target_height))
            fast_clip.close()  # Uvolni memory
        else:
            final_clip = fast_clip
        
        # Zavři přípravné klipy
        base_clip.close()
        prepared_clip.close()
        
        print(f"✅ SUPER RYCHLÝ Ken Burns efekt s ANIMACÍ vytvořen za {duration}s")
        return final_clip
        
    except Exception as e:
        print(f"❌ Chyba při vytváření super rychlého Ken Burns efektu: {e}")
        # Fallback na statický obrázek
        print("🔄 Fallback na statický obrázek...")
        try:
            static_clip = ImageClip(image_path, duration=duration)
            return static_clip.resized((target_width, target_height))
        except Exception as fallback_error:
            print(f"❌ I fallback selhal: {fallback_error}")
            raise Exception(f"Nelze vytvořit ani statický klip: {fallback_error}")

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'OK', 'message': 'FINAL FIXED Backend běží'})

@app.route('/api/list-all-images', methods=['GET'])
def list_all_images():
    """Seznam všech obrázků"""
    try:
        images = []
        projects = set()
        
        if os.path.exists(IMAGES_FOLDER):
            for filename in os.listdir(IMAGES_FOLDER):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                    # Zjisti projekt z názvu souboru (např. video_project_01.png -> video_project)
                    project_name = 'video_project'  # výchozí
                    if '_' in filename:
                        parts = filename.split('_')
                        if len(parts) >= 2:
                            project_name = '_'.join(parts[:-1])
                    
                    projects.add(project_name)
                    
                    images.append({
                        'filename': filename,
                        'path': f'/api/images/{filename}',
                        'project_name': project_name
                    })
        
        return jsonify({
            'success': True,
            'images': images,
            'total_images': len(images),
            'total_projects': len(projects)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/images/<filename>')
def serve_image(filename):
    """Vrať obrázek"""
    try:
        return send_file(os.path.join(IMAGES_FOLDER, filename))
    except Exception as e:
        return jsonify({'error': str(e)}), 404

@app.route('/api/list-backgrounds', methods=['GET'])
def list_backgrounds():
    """Seznam pozadí"""
    try:
        backgrounds = []
        if os.path.exists(BACKGROUNDS_FOLDER):
            for filename in os.listdir(BACKGROUNDS_FOLDER):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                    backgrounds.append({
                        'filename': filename,
                        'path': f'/api/backgrounds/{filename}'
                    })
        return jsonify(backgrounds)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/backgrounds/<filename>')
def serve_background(filename):
    """Vrať pozadí"""
    try:
        return send_file(os.path.join(BACKGROUNDS_FOLDER, filename))
    except Exception as e:
        return jsonify({'error': str(e)}), 404

@app.route('/api/list-video-backgrounds', methods=['GET'])
def list_video_backgrounds():
    """Seznam video pozadí"""
    try:
        backgrounds = []
        if os.path.exists(VIDEO_BACKGROUNDS_FOLDER):
            for filename in os.listdir(VIDEO_BACKGROUNDS_FOLDER):
                if filename.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                    backgrounds.append({
                        'filename': filename,
                        'path': f'/api/video-backgrounds/{filename}'
                    })
        return jsonify(backgrounds)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/video-backgrounds/<filename>')
def serve_video_background(filename):
    """Vrať video pozadí"""
    try:
        return send_file(os.path.join(VIDEO_BACKGROUNDS_FOLDER, filename))
    except Exception as e:
        return jsonify({'error': str(e)}), 404

@app.route('/api/files', methods=['GET'])
def list_files():
    """Seznam souborů"""
    try:
        files = []
        if os.path.exists(UPLOAD_FOLDER):
            for filename in os.listdir(UPLOAD_FOLDER):
                if filename.lower().endswith(('.mp3', '.wav', '.m4a', '.aac')):
                    files.append({
                        'filename': filename,
                        'path': f'/api/files/{filename}'
                    })
        return jsonify(files)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/test-ken-burns', methods=['POST'])
def test_ken_burns():
    """Test Ken Burns efektu"""
    try:
        data = request.get_json()
        image_name = data.get('image', 'video_project_01.png')
        
        print(f"🧪 TEST: Testuji Ken Burns efekt pro {image_name}")
        
        image_path = os.path.join(IMAGES_FOLDER, image_name)
        if not os.path.exists(image_path):
            return jsonify({'error': f'Obrázek neexistuje: {image_path}'}), 404
        
        # Vytvoř Ken Burns efekt
        clip = create_ken_burns_effect(image_path, 3.0, 1280, 720, effect_type=0)
        
        # Export
        timestamp = datetime.now().strftime('%H%M%S')
        output_path = os.path.join(OUTPUT_FOLDER, f'test_ken_burns_{timestamp}.mp4')
        
        print(f"🧪 TEST: Exportuji do {output_path}")
        clip.write_videofile(output_path, fps=24, codec='libx264')
        
        file_size = os.path.getsize(output_path)
        print(f"✅ TEST: Export úspěšný! Velikost: {file_size} bytes")
        
        return jsonify({
            'success': True,
            'message': 'Ken Burns test úspěšný',
            'file_size': file_size,
            'download_url': f'/api/download/{os.path.basename(output_path)}'
        })
        
    except Exception as e:
        print(f"❌ TEST FAILED: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/test-fast-ken-burns', methods=['POST'])
def test_fast_ken_burns():
    """⚡ TEST RYCHLÉ Ken Burns efektu"""
    try:
        data = request.get_json()
        image_name = data.get('image', 'video_project_01.png')
        effect_type = data.get('effect_type', 0)  # 0=zoom_in, 1=zoom_out, 2=pan_left, 3=pan_right
        
        print(f"⚡ RYCHLÝ TEST: Testuji RYCHLÉ Ken Burns efekt pro {image_name}, efekt {effect_type}")
        
        image_path = os.path.join(IMAGES_FOLDER, image_name)
        if not os.path.exists(image_path):
            return jsonify({'error': f'Obrázek neexistuje: {image_path}'}), 404
        
        # Vytvoř RYCHLÝ Ken Burns efekt
        clip = create_fast_ken_burns_effect(image_path, 3.0, 1280, 720, effect_type)
        
        # Export
        timestamp = datetime.now().strftime('%H%M%S')
        output_path = os.path.join(OUTPUT_FOLDER, f'test_FAST_ken_burns_{timestamp}.mp4')
        
        print(f"⚡ RYCHLÝ TEST: Exportuji do {output_path}")
        clip.write_videofile(output_path, fps=15, codec='libx264')
        
        file_size = os.path.getsize(output_path)
        print(f"✅ RYCHLÝ TEST: Export úspěšný! Velikost: {file_size} bytes")
        
        return jsonify({
            'success': True,
            'message': 'Rychlý Ken Burns test úspěšný',
            'file_size': file_size,
            'download_url': f'/api/download/{os.path.basename(output_path)}'
        })
        
    except Exception as e:
        print(f"❌ RYCHLÝ TEST FAILED: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/preview-ken-burns', methods=['POST'])
def preview_ken_burns():
    """Preview Ken Burns efektů"""
    try:
        data = request.get_json()
        images = data.get('images', [])
        preview_settings = data.get('preview_settings', {})
        
        print(f"🔥 PREVIEW: Začínám preview s {len(images)} obrázky")
        
        if not images:
            return jsonify({
                'success': False,
                'error': 'Chybí obrázky',
                'total_previews': 0,
                'successful_clips': 0,
                'message': 'Nebyl poskytnut žádný obrázek k zpracování'
            }), 400
        
        # Nastavení
        duration_per_image = preview_settings.get('duration', 4.0)
        width = preview_settings.get('width', 1280)
        height = preview_settings.get('height', 720)
        
        clips = []
        effect_types = [0, 1, 2, 3]  # zoom_in, zoom_out, pan_left, pan_right
        
        for i, image_info in enumerate(images):
            filename = image_info.get('filename')
            if not filename:
                continue
                
            image_path = os.path.join(IMAGES_FOLDER, filename)
            if not os.path.exists(image_path):
                print(f"❌ PREVIEW: Obrázek neexistuje: {image_path}")
                continue
            
            # Střídej efekty
            effect_type = effect_types[i % len(effect_types)]
            effect_names = ['Zoom In', 'Zoom Out', 'Pan Left', 'Pan Right']
            
            print(f"🎬 PREVIEW: Vytvářím {effect_names[effect_type]} pro {filename}")
            
            try:
                clip = create_ken_burns_effect(image_path, duration_per_image, width, height, effect_type)
                clips.append(clip)
                print(f"✅ PREVIEW: Klip {i+1} úspěšně vytvořen")
            except Exception as e:
                print(f"❌ PREVIEW: Chyba při vytváření klipu {i+1}: {e}")
                continue
        
        if not clips:
            print(f"❌ PREVIEW: Žádné klipy se nepodařilo vytvořit")
            return jsonify({
                'success': False,
                'error': 'Nepodařilo se vytvořit žádné klipy',
                'total_previews': 0,
                'successful_clips': 0,
                'message': 'Všechny klipy selhaly při vytváření'
            }), 500
        
        print(f"🔥 PREVIEW: Spojuji {len(clips)} klipů")
        
        try:
            # Spojení klipů
            final_video = concatenate_videoclips(clips)
            
            # Export
            timestamp = datetime.now().strftime('%H%M%S')
            output_path = os.path.join(OUTPUT_FOLDER, f'test_preview_{timestamp}.mp4')
            
            print(f"🔥 PREVIEW: Exportuji do {output_path}")
            final_video.write_videofile(output_path, fps=24, codec='libx264')
            
            file_size = os.path.getsize(output_path)
            print(f"✅ PREVIEW: Export úspěšný! Velikost: {file_size} bytes")
            
            return jsonify({
                'success': True,
                'message': f'Preview vytvořen s {len(clips)} Ken Burns efekty',
                'total_previews': len(images),
                'successful_clips': len(clips),
                'file_size': file_size,
                'download_url': f'/api/download/{os.path.basename(output_path)}'
            })
            
        except Exception as export_error:
            print(f"❌ PREVIEW: Chyba při exportu: {export_error}")
            return jsonify({
                'success': False,
                'error': f'Chyba při exportu videa: {export_error}',
                'total_previews': len(images),
                'successful_clips': len(clips),
                'message': f'Vytvořeno {len(clips)} klipů, ale export selhal'
            }), 500
        
    except Exception as e:
        print(f"❌ PREVIEW FAILED: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'total_previews': len(images) if 'images' in locals() else 0,
            'successful_clips': 0,
            'message': 'Generální chyba při vytváření preview'
        }), 500

@app.route('/api/fast-preview-ken-burns', methods=['POST'])
def fast_preview_ken_burns():
    """⚡ RYCHLÝ Preview Ken Burns efektů - používá optimalizované efekty"""
    try:
        data = request.get_json()
        images = data.get('images', [])
        preview_settings = data.get('preview_settings', {})
        
        print(f"⚡ RYCHLÝ PREVIEW: Začínám rychlý preview s {len(images)} obrázky")
        
        if not images:
            return jsonify({
                'success': False,
                'error': 'Chybí obrázky',
                'total_previews': 0,
                'successful_clips': 0,
                'message': 'Nebyl poskytnut žádný obrázek k zpracování'
            }), 400
        
        # Nastavení pro rychlý náhled
        duration_per_image = preview_settings.get('duration', 2.0)  # Kratší náhled
        width = preview_settings.get('width', 720)  # Menší rozlišení
        height = preview_settings.get('height', 480)
        
        clips = []
        effect_types = [0, 1, 2, 3]  # zoom_in, zoom_out, pan_left, pan_right
        
        for i, image_info in enumerate(images[:5]):  # Pouze prvních 5 obrázků pro rychlost
            filename = image_info.get('filename')
            if not filename:
                continue
                
            image_path = os.path.join(IMAGES_FOLDER, filename)
            if not os.path.exists(image_path):
                print(f"❌ RYCHLÝ PREVIEW: Obrázek neexistuje: {image_path}")
                continue
            
            # Střídej efekty
            effect_type = effect_types[i % len(effect_types)]
            effect_names = ['Zoom In', 'Zoom Out', 'Pan Left', 'Pan Right']
            
            print(f"⚡ RYCHLÝ PREVIEW: Vytvářím {effect_names[effect_type]} pro {filename}")
            
            try:
                # POUŽIJ RYCHLÉ Ken Burns efekty
                clip = create_fast_ken_burns_effect(image_path, duration_per_image, width, height, effect_type)
                clips.append(clip)
                print(f"✅ RYCHLÝ PREVIEW: Klip {i+1} úspěšně vytvořen")
            except Exception as e:
                print(f"❌ RYCHLÝ PREVIEW: Chyba při vytváření klipu {i+1}: {e}")
                continue
        
        if not clips:
            print(f"❌ RYCHLÝ PREVIEW: Žádné klipy se nepodařilo vytvořit")
            return jsonify({
                'success': False,
                'error': 'Nepodařilo se vytvořit žádné klipy',
                'total_previews': 0,
                'successful_clips': 0
            }), 500
        
        print(f"⚡ RYCHLÝ PREVIEW: Spojuji {len(clips)} klipů")
        
        try:
            final_video = concatenate_videoclips(clips)
            
            # Export videa s nižšími nastaveními pro rychlost
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_filename = f'fast_preview_{timestamp}.mp4'
            output_path = os.path.join(OUTPUT_FOLDER, output_filename)
            
            print(f"⚡ RYCHLÝ PREVIEW: Exportuji do {output_path}")
            
            # Nižší FPS a rychlejší nastavení
            final_video.write_videofile(output_path, fps=15, codec='libx264')
            
            file_size = os.path.getsize(output_path)
            print(f"✅ RYCHLÝ PREVIEW: Video úspěšně vytvořeno! Velikost: {file_size} bytes")
            
            return jsonify({
                'success': True,
                'message': f'Rychlý preview úspěšně vygenerován',
                'total_previews': 1,
                'successful_clips': len(clips),
                'file_size': file_size,
                'preview_file': output_filename,
                'download_url': f'/api/download/{output_filename}',
                'duration': final_video.duration,
                'preview_duration': final_video.duration,
                'resolution': f'{width}x{height}',
                'total_clips': len(clips),
                'note': f'Rychlý náhled pouze prvních {len(clips)} obrázků'
            })
            
        except Exception as e:
            print(f"❌ RYCHLÝ PREVIEW: Chyba při exportu: {e}")
            return jsonify({
                'success': False,
                'error': f'Chyba při exportu rychlého náhledu: {str(e)}',
                'total_previews': 0,
                'successful_clips': len(clips)
            }), 500
            
    except Exception as e:
        print(f"❌ RYCHLÝ PREVIEW: Kritická chyba: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'total_previews': 0,
            'successful_clips': 0
        }), 500

@app.route('/api/download/<filename>')
def download_file(filename):
    """Stáhni soubor z output/ nebo uploads/"""
    try:
        # Zkus nejprve output folder (pro videa)
        output_path = os.path.join(OUTPUT_FOLDER, filename)
        if os.path.exists(output_path):
            return send_file(output_path, as_attachment=True)
        
        # Pokud není v output/, zkus uploads/ (pro MP3)
        upload_path = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(upload_path):
            return send_file(upload_path, as_attachment=True)
        
        # Soubor nenalezen
        return jsonify({'error': f'Soubor {filename} nenalezen'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 404

def allowed_image_file(filename):
    """Zkontroluj, jestli je soubor povolený obrázek"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp']

@app.route('/api/generate-images', methods=['POST'])
def generate_images():
    """
    Endpoint pro skutečné generování obrázků pomocí DALL-E 3
    """
    try:
        data = request.get_json()
        project_name = data.get('project_name', 'video_project')
        prompts = data.get('prompts', [])
        json_blocks = data.get('json_blocks', {})
        custom_image_count = data.get('custom_image_count')
        
        # Pokud nemáme prompty ale máme json_blocks, vygenerujeme prompty z nich
        if not prompts and json_blocks:
            prompts = []
            for block_key, block_data in json_blocks.items():
                if isinstance(block_data, dict) and 'text' in block_data:
                    # Vytvoř vizuální prompt z textového obsahu
                    text_content = block_data['text']
                    visual_prompt = f"Documentary style photograph, cinematic lighting, high quality: {text_content[:200]}"
                    prompts.append(visual_prompt)
                elif isinstance(block_data, str):
                    # Pokud je to přímo string
                    visual_prompt = f"Documentary style photograph, cinematic lighting, high quality: {block_data[:200]}"
                    prompts.append(visual_prompt)
        
        # Omez počet promptů podle custom_image_count
        if custom_image_count and isinstance(custom_image_count, int) and custom_image_count > 0:
            prompts = prompts[:custom_image_count]
            print(f"🔢 Omezuji počet obrázků na {custom_image_count} podle uživatelského nastavení")
        
        if not prompts:
            return jsonify({'error': 'Žádné prompty pro generování obrázků'}), 400
        
        print(f"🎨 Generuji {len(prompts)} obrázků pro projekt: {project_name}")
        
        generated_images = []
        failed_images = []
        
        for i, prompt in enumerate(prompts, 1):
            print(f"🔄 Generuji obrázek {i}/{len(prompts)}: {prompt[:50]}...")
            
            # Generuj obrázek pomocí DALL-E
            result = generate_dalle_images(prompt, size="1792x1024")
            
            if result.get('success'):
                # Stáhni a ulož obrázek
                images = result.get('images', [])
                if images:
                    image_url = images[0]['url']
                    filename = f"{project_name}_{i:02d}.png"
                    
                    # Stáhni obrázek
                    download_result = download_image_from_url(image_url, filename, IMAGES_FOLDER)
                    
                    if download_result.get('success'):
                        generated_images.append({
                            'filename': filename,
                            'prompt': prompt,
                            'url': image_url,
                            'file_size': download_result.get('file_size'),
                            'project_name': project_name
                        })
                        print(f"✅ Obrázek {i} úspěšně vygenerován a uložen: {filename}")
                    else:
                        failed_images.append({
                            'prompt': prompt,
                            'error': download_result.get('error', 'Neznámá chyba při stahování')
                        })
                        print(f"❌ Chyba při stahování obrázku {i}: {download_result.get('error')}")
                else:
                    failed_images.append({
                        'prompt': prompt,
                        'error': 'DALL-E nevrátil žádné obrázky'
                    })
            else:
                failed_images.append({
                    'prompt': prompt,
                    'error': result.get('error', 'Neznámá chyba při generování')
                })
                print(f"❌ Chyba při generování obrázku {i}: {result.get('error')}")
        
        total_generated = len(generated_images)
        total_failed = len(failed_images)
        
        print(f"📊 Výsledek generování: {total_generated} úspěšných, {total_failed} neúspěšných")
        
        return jsonify({
            'success': total_generated > 0,
            'message': f'Vygenerováno {total_generated} obrázků, {total_failed} selhalo',
            'data': {
                'generated_images': generated_images,
                'failed_images': failed_images,
                'project_name': project_name,
                'total_generated': total_generated,
                'total_failed': total_failed
            }
        })
        
    except Exception as e:
        error_msg = f"Neočekávaná chyba při generování obrázků: {str(e)}"
        print(f"❌ {error_msg}")
        return jsonify({'error': error_msg}), 500

@app.route('/api/generate-video', methods=['POST', 'OPTIONS'])
def generate_video():
    """
    Generování finálního videa s Ken Burns efekty
    """
    if request.method == 'OPTIONS':
        # Odpověď na preflight request
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response
        
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'Žádná data nebyla poslána'
            }), 400
            
        images = data.get('images', [])
        video_settings = data.get('video_settings', {})
        
        print(f"🎬 VIDEO: Začínám generování finálního videa s {len(images)} obrázky")
        
        if not images:
            return jsonify({
                'success': False,
                'error': 'Chybí obrázky pro video',
                'total_videos': 0,
                'successful_clips': 0,
                'message': 'Nebyl poskytnut žádný obrázek k zpracování'
            }), 400
        
        # Nastavení videa
        duration_per_image = video_settings.get('duration', 4.0)
        width = video_settings.get('width', 1280)
        height = video_settings.get('height', 720)
        
        clips = []
        effect_types = [0, 1, 2, 3]  # zoom_in, zoom_out, pan_left, pan_right
        
        for i, image_info in enumerate(images):
            filename = image_info.get('filename')
            if not filename:
                continue
                
            image_path = os.path.join(IMAGES_FOLDER, filename)
            if not os.path.exists(image_path):
                print(f"❌ VIDEO: Obrázek neexistuje: {image_path}")
                continue
            
            # Střídej efekty
            effect_type = effect_types[i % len(effect_types)]
            effect_names = ['Zoom In', 'Zoom Out', 'Pan Left', 'Pan Right']
            
            print(f"🎬 VIDEO: Vytvářím {effect_names[effect_type]} pro {filename}")
            
            try:
                clip = create_ken_burns_effect(image_path, duration_per_image, width, height, effect_type)
                clips.append(clip)
                print(f"✅ VIDEO: Klip {i+1} úspěšně vytvořen")
            except Exception as e:
                print(f"❌ VIDEO: Chyba při vytváření klipu {i+1}: {e}")
                continue
        
        if not clips:
            print(f"❌ VIDEO: Žádné klipy se nepodařilo vytvořit")
            return jsonify({
                'success': False,
                'error': 'Nepodařilo se vytvořit žádné klipy',
                'total_videos': 0,
                'successful_clips': 0,
                'message': 'Všechny klipy selhaly při vytváření'
            }), 500
        
        print(f"🎬 VIDEO: Spojuji {len(clips)} klipů do finálního videa")
        
        try:
            # Spojení klipů
            final_video = concatenate_videoclips(clips)
            
            # Export finálního videa
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_filename = f'final_video_{timestamp}.mp4'
            output_path = os.path.join(OUTPUT_FOLDER, output_filename)
            
            print(f"🎬 VIDEO: Exportuji finální video do {output_path}")
            final_video.write_videofile(output_path, fps=24, codec='libx264')
            
            file_size = os.path.getsize(output_path)
            print(f"✅ VIDEO: Finální video úspěšně vytvořeno! Velikost: {file_size} bytes")
            
            return jsonify({
                'success': True,
                'message': f'Finální video úspěšně vygenerováno s {len(clips)} Ken Burns efekty',
                'total_videos': 1,
                'successful_clips': len(clips),
                'file_size': file_size,
                'filename': output_filename,
                'download_url': f'/api/download/{output_filename}',
                'duration': len(clips) * duration_per_image
            })
            
        except Exception as e:
            print(f"❌ VIDEO ERROR při exportu: {e}")
            return jsonify({
                'success': False,
                'error': f'Chyba při exportu finálního videa: {str(e)}',
                'total_videos': 0,
                'successful_clips': len(clips)
            }), 500
            
    except Exception as e:
        print(f"❌ VIDEO CRITICAL ERROR: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'total_videos': 0,
            'successful_clips': 0
        }), 500

@app.route('/api/generate-video-with-audio', methods=['POST', 'OPTIONS'])
def generate_video_with_audio():
    """
    NOVÝ: Generování videa s MP3 audio soubory - RYCHLÉ a SPRÁVNÉ
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response
        
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'Žádná data nebyla poslána'
            }), 400
            
        images = data.get('images', [])
        project_name = data.get('project_name', 'video_project')
        video_settings = data.get('video_settings', {})
        # NOVÉ: max_mp3_files umožňuje určit, kolik MP3 souborů použít (0 = všechny)
        max_mp3_files = data.get('max_mp3_files', 0)
        
        print(f"🎬 AUDIO VIDEO: Začínám generování s {len(images)} obrázky a MP3 soubory")
        
        if not images:
            return jsonify({
                'success': False,
                'error': 'Chybí obrázky pro video'
            }), 400
        
        # Najdi všechny Narrator MP3 soubory
        narrator_files = []
        for filename in os.listdir(UPLOAD_FOLDER):
            if filename.startswith('Narrator_') and filename.endswith('.mp3'):
                narrator_files.append(filename)
        
        narrator_files.sort()  # Seřadí podle čísel
        
        # Omez počet MP3 souborů, pokud je nastaven max_mp3_files (>0)
        total_files_found = len(narrator_files)
        if isinstance(max_mp3_files, int) and max_mp3_files > 0 and len(narrator_files) > max_mp3_files:
            narrator_files = narrator_files[:max_mp3_files]
            print(f"🎬 RYCHLÉ VIDEO: Použiju pouze prvních {max_mp3_files} MP3 souborů z {total_files_found} celkem")
        
        print(f"🎵 Použiju {len(narrator_files)} Narrator MP3 souborů pro rychlé video")
        
        if not narrator_files:
            print("⚠️ Žádné Narrator MP3 - vytvořím tiché video")
            # Fallback na původní metodu
            return generate_video()
        
        # Načti audio soubory a spočítej jejich délky
        audio_clips = []
        total_audio_duration = 0
        
        for audio_file in narrator_files:
            try:
                audio_path = os.path.join(UPLOAD_FOLDER, audio_file)
                audio_clip = AudioFileClip(audio_path)
                audio_clips.append(audio_clip)
                total_audio_duration += audio_clip.duration
                print(f"📄 {audio_file}: {audio_clip.duration:.2f}s")
            except Exception as e:
                print(f"❌ Chyba při načítání {audio_file}: {e}")
                continue
        
        print(f"🎵 Celková délka audio: {total_audio_duration:.2f}s ({total_audio_duration/60:.1f} minut)")
        
        # Spoj všechna audio dohromady
        if audio_clips:
            final_audio = concatenate_audioclips(audio_clips)
        else:
            print("❌ Žádné audio se nepodařilo načíst")
            return jsonify({'success': False, 'error': 'Nepodařilo se načíst žádné audio soubory'}), 500
        
        # Vypočítej délku na obrázek
        duration_per_image = total_audio_duration / len(images)
        print(f"📊 Délka na obrázek: {duration_per_image:.2f}s")
        
        # Nastavení videa  
        width = video_settings.get('width', 1280)
        height = video_settings.get('height', 720)
        
        # OPTIMALIZOVANÉ VYTVOŘENÍ VIDEO KLIPŮ - bez náročných Ken Burns efektů
        video_clips = []
        
        for i, image_info in enumerate(images):
            filename = image_info.get('filename')
            if not filename:
                continue
                
            image_path = os.path.join(IMAGES_FOLDER, filename)
            if not os.path.exists(image_path):
                print(f"❌ Obrázek neexistuje: {image_path}")
                continue
            
            print(f"🖼️  Vytvářím klip {i+1}/{len(images)}: {filename} ({duration_per_image:.2f}s)")
            
            try:
                # JEDNODUCHÝ ImageClip - mnohem rychlejší než Ken Burns
                image_clip = ImageClip(image_path, duration=duration_per_image)
                
                # Změň velikost na požadované rozměry
                image_clip = image_clip.resized((width, height))
                
                video_clips.append(image_clip)
                print(f"✅ Klip {i+1} vytvořen")
                
            except Exception as e:
                print(f"❌ Chyba při vytváření klipu {i+1}: {e}")
                continue
        
        if not video_clips:
            print("❌ Žádné video klipy se nepodařilo vytvořit")
            return jsonify({
                'success': False,
                'error': 'Nepodařilo se vytvořit žádné video klipy'
            }), 500
        
        print(f"🎬 Spojuji {len(video_clips)} video klipů")
        
        try:
            # Spoj video klipy
            final_video = concatenate_videoclips(video_clips)
            
            # Přidej audio stopu k videu
            final_video_with_audio = final_video.with_audio(final_audio)
            
            # Export finálního videa
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_filename = f'final_video_with_audio_{timestamp}.mp4'
            output_path = os.path.join(OUTPUT_FOLDER, output_filename)
            
            print(f"🎬 Exportuji finální video s audio do {output_path}")
            print(f"📊 Video délka: {final_video.duration:.2f}s, Audio délka: {final_audio.duration:.2f}s")
            
            # Export s audio
            final_video_with_audio.write_videofile(
                output_path, 
                fps=24, 
                codec='libx264',
                audio_codec='aac'
            )
            
            file_size = os.path.getsize(output_path)
            print(f"✅ FINÁLNÍ VIDEO s audio úspěšně vytvořeno! Velikost: {file_size} bytes")
            
            return jsonify({
                'success': True,
                'message': f'Video s audio úspěšně vygenerováno',
                'total_videos': 1,
                'successful_clips': len(video_clips),
                'file_size': file_size,
                'filename': output_filename,
                'download_url': f'/api/download/{output_filename}',
                'duration': final_video.duration,
                'audio_duration': final_audio.duration,
                'total_mp3_files': len(narrator_files),
                'duration_per_image': duration_per_image
            })
            
        except Exception as e:
            print(f"❌ CHYBA při exportu videa s audio: {e}")
            return jsonify({
                'success': False,
                'error': f'Chyba při exportu videa s audio: {str(e)}',
                'total_videos': 0,
                'successful_clips': len(video_clips)
            }), 500
            
    except Exception as e:
        print(f"❌ KRITICKÁ CHYBA: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'total_videos': 0,
            'successful_clips': 0
        }), 500

@app.route('/api/generate-video-kenburns-with-audio', methods=['POST', 'OPTIONS'])
def generate_video_kenburns_with_audio():
    """
    NOVÝ: Generování videa s Ken Burns efekty A s MP3 audio soubory
    Kombinuje krásné animace s audio integrací
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response
        
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'Žádná data nebyla poslána'
            }), 400
            
        images = data.get('images', [])
        project_name = data.get('project_name', 'video_project')
        video_settings = data.get('video_settings', {})
        # NOVÉ: max_mp3_files umožňuje určit, kolik MP3 souborů použít (0 = všechny)
        max_mp3_files = data.get('max_mp3_files', 0)
        
        print(f"🎭 KEN BURNS AUDIO: Začínám generování s {len(images)} obrázky s efekty a MP3 soubory")
        
        if not images:
            return jsonify({
                'success': False,
                'error': 'Chybí obrázky pro video'
            }), 400
        
        # Najdi všechny Narrator MP3 soubory
        narrator_files = []
        for filename in os.listdir(UPLOAD_FOLDER):
            if filename.startswith('Narrator_') and filename.endswith('.mp3'):
                narrator_files.append(filename)
        
        narrator_files.sort()  # Seřadí podle čísel
        
        # Omez počet MP3 souborů, pokud je nastaven max_mp3_files (>0)
        total_files_found = len(narrator_files)
        if isinstance(max_mp3_files, int) and max_mp3_files > 0 and len(narrator_files) > max_mp3_files:
            narrator_files = narrator_files[:max_mp3_files]
            print(f"🎭 STANDARDNÍ KEN BURNS: Použiju pouze prvních {max_mp3_files} MP3 souborů z {total_files_found} celkem")
        
        print(f"🎵 Použiju {len(narrator_files)} Narrator MP3 souborů pro standardní Ken Burns")
        
        if not narrator_files:
            print("⚠️ Žádné Narrator MP3 - vytvořím tiché Ken Burns video")
            # Fallback na původní metodu
            return generate_video()
        
        # Načti audio soubory a spočítej jejich délky
        audio_clips = []
        total_audio_duration = 0
        
        for audio_file in narrator_files:
            try:
                audio_path = os.path.join(UPLOAD_FOLDER, audio_file)
                audio_clip = AudioFileClip(audio_path)
                audio_clips.append(audio_clip)
                total_audio_duration += audio_clip.duration
                print(f"📄 {audio_file}: {audio_clip.duration:.2f}s")
            except Exception as e:
                print(f"❌ Chyba při načítání {audio_file}: {e}")
                continue
        
        print(f"🎵 Celková délka audio: {total_audio_duration:.2f}s ({total_audio_duration/60:.1f} minut)")
        
        # Spoj všechna audio dohromady
        if audio_clips:
            final_audio = concatenate_audioclips(audio_clips)
        else:
            print("❌ Žádné audio se nepodařilo načíst")
            return jsonify({'success': False, 'error': 'Nepodařilo se načíst žádné audio soubory'}), 500
        
        # Vypočítej délku na obrázek
        duration_per_image = total_audio_duration / len(images)
        print(f"📊 Délka na obrázek: {duration_per_image:.2f}s")
        
        # Nastavení videa  
        width = video_settings.get('width', 1280)
        height = video_settings.get('height', 720)
        
        # VYTVOŘENÍ VIDEO KLIPŮ s Ken Burns efekty
        video_clips = []
        effect_types = [0, 1, 2, 3]  # zoom_in, zoom_out, pan_left, pan_right
        
        for i, image_info in enumerate(images):
            filename = image_info.get('filename')
            if not filename:
                continue
                
            image_path = os.path.join(IMAGES_FOLDER, filename)
            if not os.path.exists(image_path):
                print(f"❌ Obrázek neexistuje: {image_path}")
                continue
            
            # Střídej efekty nebo použij uživatelský výběr
            kenBurnsSequence = image_info.get('kenBurnsSequence', None)
            if kenBurnsSequence:
                # Použij první efekt ze sekvence uživatele
                effect_mapping = {
                    'zoom_in': 0,
                    'zoom_out': 1, 
                    'pan_left': 2,
                    'pan_right': 3
                }
                effect_type = effect_mapping.get(kenBurnsSequence[0], 0)
            else:
                # Výchozí střídání efektů
                effect_type = effect_types[i % len(effect_types)]
                
            effect_names = ['Zoom In', 'Zoom Out', 'Pan Left', 'Pan Right']
            
            print(f"🎭 Ken Burns: Vytvářím {effect_names[effect_type]} pro {filename} ({duration_per_image:.2f}s)")
            
            try:
                # POUŽITÍ Ken Burns efektů s délkou podle audio
                clip = create_ken_burns_effect(image_path, duration_per_image, width, height, effect_type)
                video_clips.append(clip)
                print(f"✅ Ken Burns klip {i+1} vytvořen")
                
            except Exception as e:
                print(f"❌ Chyba při vytváření Ken Burns klipu {i+1}: {e}")
                continue
        
        if not video_clips:
            print("❌ Žádné video klipy se nepodařilo vytvořit")
            return jsonify({
                'success': False,
                'error': 'Nepodařilo se vytvořit žádné video klipy'
            }), 500
        
        print(f"🎬 Spojuji {len(video_clips)} video klipů s Ken Burns efekty")
        
        try:
            # Spoj video klipy
            final_video = concatenate_videoclips(video_clips)
            
            # Přidej audio stopu k videu
            final_video_with_audio = final_video.with_audio(final_audio)
            
            # Export finálního videa
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_filename = f'final_kenburns_with_audio_{timestamp}.mp4'
            output_path = os.path.join(OUTPUT_FOLDER, output_filename)
            
            print(f"🎭 Exportuji Ken Burns video s audio do {output_path}")
            print(f"📊 Video délka: {final_video.duration:.2f}s, Audio délka: {final_audio.duration:.2f}s")
            
            # Export s audio
            final_video_with_audio.write_videofile(
                output_path, 
                fps=24, 
                codec='libx264',
                audio_codec='aac'
            )
            
            file_size = os.path.getsize(output_path)
            print(f"✅ FINÁLNÍ Ken Burns VIDEO s audio úspěšně vytvořeno! Velikost: {file_size} bytes")
            
            return jsonify({
                'success': True,
                'message': f'Ken Burns video s audio úspěšně vygenerováno',
                'total_videos': 1,
                'successful_clips': len(video_clips),
                'file_size': file_size,
                'filename': output_filename,
                'download_url': f'/api/download/{output_filename}',
                'duration': final_video.duration,
                'audio_duration': final_audio.duration,
                'total_mp3_files': len(narrator_files),
                'duration_per_image': duration_per_image
            })
            
        except Exception as e:
            print(f"❌ CHYBA při exportu Ken Burns videa s audio: {e}")
            return jsonify({
                'success': False,
                'error': f'Chyba při exportu Ken Burns videa s audio: {str(e)}',
                'total_videos': 0,
                'successful_clips': len(video_clips)
            }), 500
            
    except Exception as e:
        print(f"❌ KRITICKÁ CHYBA: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'total_videos': 0,
            'successful_clips': 0
        }), 500

@app.route('/api/generate-video-fast-kenburns-with-audio', methods=['POST', 'OPTIONS'])
def generate_video_fast_kenburns_with_audio():
    """
    ⚡ NOVÝ: Generování videa s RYCHLÝMI Ken Burns efekty A s MP3 audio soubory
    3-5x rychlejší než standardní Ken Burns, ale stále s efekty!
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response
        
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'Žádná data nebyla poslána'
            }), 400
            
        images = data.get('images', [])
        project_name = data.get('project_name', 'video_project')
        video_settings = data.get('video_settings', {})
        # NOVÉ: max_mp3_files umožňuje určit, kolik MP3 souborů použít (0 nebo záporné = všechny)
        max_mp3_files = data.get('max_mp3_files', 0)
        
        print(f"⚡ RYCHLÉ KEN BURNS AUDIO: Začínám generování s {len(images)} obrázky s rychlými efekty a MP3 soubory")
        
        if not images:
            return jsonify({
                'success': False,
                'error': 'Chybí obrázky pro video'
            }), 400
        
        # Najdi všechny Narrator MP3 soubory
        narrator_files = []
        for filename in os.listdir(UPLOAD_FOLDER):
            if filename.startswith('Narrator_') and filename.endswith('.mp3'):
                narrator_files.append(filename)
        
        narrator_files.sort()  # Seřadí podle čísel
        
        # RYCHLÁ VERZE: Omez počet MP3 souborů, pokud je nastaven max_mp3_files (>0)
        total_files_found = len(narrator_files)
        if isinstance(max_mp3_files, int) and max_mp3_files > 0 and len(narrator_files) > max_mp3_files:
            narrator_files = narrator_files[:max_mp3_files]
            print(f"⚡ RYCHLÁ VERZE: Použiju pouze prvních {max_mp3_files} MP3 souborů z {total_files_found} celkem")
        
        print(f"🎵 Použiju {len(narrator_files)} Narrator MP3 souborů pro rychlé Ken Burns")
        
        if not narrator_files:
            print("⚠️ Žádné Narrator MP3 - vytvořím rychlé video")
            # Fallback na rychlou metodu
            return generate_video_with_audio()
        
        # Načti audio soubory a spočítej jejich délky
        audio_clips = []
        total_audio_duration = 0
        
        for audio_file in narrator_files:
            try:
                audio_path = os.path.join(UPLOAD_FOLDER, audio_file)
                audio_clip = AudioFileClip(audio_path)
                audio_clips.append(audio_clip)
                total_audio_duration += audio_clip.duration
                print(f"📄 {audio_file}: {audio_clip.duration:.2f}s")
            except Exception as e:
                print(f"❌ Chyba při načítání {audio_file}: {e}")
                continue
        
        print(f"🎵 Celková délka audio: {total_audio_duration:.2f}s ({total_audio_duration/60:.1f} minut)")
        
        # Spoj všechna audio dohromady
        if audio_clips:
            final_audio = concatenate_audioclips(audio_clips)
        else:
            print("❌ Žádné audio se nepodařilo načíst")
            return jsonify({'success': False, 'error': 'Nepodařilo se načíst žádné audio soubory'}), 500
        
        # Vypočítej délku na obrázek - s možností loopování obrázků
        base_duration_per_image = total_audio_duration / len(images)
        
        # Pro rychlé Ken Burns omez na maximum 30s per obrázek, pak loop
        max_duration_per_image = 30.0
        
        if base_duration_per_image > max_duration_per_image:
            # Spočítej kolikrát musíme obrázky zopakovat
            loop_factor = int(base_duration_per_image / max_duration_per_image) + 1
            duration_per_image = total_audio_duration / (len(images) * loop_factor)
            print(f"🔄 LOOP: Audio příliš dlouhé ({base_duration_per_image:.1f}s/obrázek)")
            print(f"🔄 ŘEŠENÍ: Obrázky se zopakují {loop_factor}x pro pokrytí {total_audio_duration:.1f}s")
            print(f"📊 Nová délka na obrázek: {duration_per_image:.2f}s")
            
            # Vytvoř loopované obrázky
            looped_images = []
            for loop_i in range(loop_factor):
                for img in images:
                    looped_images.append({
                        **img,
                        'loop_iteration': loop_i,
                        'original_filename': img.get('filename')
                    })
            images = looped_images
            print(f"🔄 Vytvořeno {len(images)} loopovaných obrázků (původně {len(images)//loop_factor})")
        else:
            duration_per_image = base_duration_per_image
            print(f"📊 Délka na obrázek: {duration_per_image:.2f}s (bez loop)")
        
        print(f"🎬 Celkové video klipů k vytvoření: {len(images)}")
        
        # Nastavení videa  
        width = video_settings.get('width', 1280)
        height = video_settings.get('height', 720)
        
        # VYTVOŘENÍ VIDEO KLIPŮ s RYCHLÝMI Ken Burns efekty
        video_clips = []
        effect_types = [0, 1, 2, 3]  # zoom_in, zoom_out, pan_left, pan_right
        
        for i, image_info in enumerate(images):
            filename = image_info.get('filename')
            original_filename = image_info.get('original_filename', filename)
            loop_iteration = image_info.get('loop_iteration', 0)
            
            if not filename:
                continue
                
            image_path = os.path.join(IMAGES_FOLDER, filename)
            if not os.path.exists(image_path):
                print(f"❌ Obrázek neexistuje: {image_path}")
                continue
            
            # VŽDY STŘÍDEJ VŠECHNY EFEKTY pro rychlou verzi - ignoruj uživatelské nastavení
            # Zajisti kontinuitu přes loopy - každý klip má jiný efekt
            effect_type = effect_types[i % len(effect_types)]
                
            effect_names = ['Zoom In', 'Zoom Out', 'Pan Left', 'Pan Right']
            
            loop_suffix = f" (loop {loop_iteration + 1})" if loop_iteration > 0 else ""
            print(f"⚡ Rychlé Ken Burns: Vytvářím {effect_names[effect_type]} pro {original_filename}{loop_suffix} ({duration_per_image:.2f}s)")
            
            try:
                # POUŽITÍ RYCHLÝCH Ken Burns efektů s délkou podle audio
                clip = create_fast_ken_burns_effect(image_path, duration_per_image, width, height, effect_type)
                video_clips.append(clip)
                print(f"✅ Rychlý Ken Burns klip {i+1} vytvořen")
                
            except Exception as e:
                print(f"❌ Chyba při vytváření rychlého Ken Burns klipu {i+1}: {e}")
                continue
        
        if not video_clips:
            print("❌ Žádné video klipy se nepodařilo vytvořit")
            return jsonify({
                'success': False,
                'error': 'Nepodařilo se vytvořit žádné video klipy'
            }), 500
        
        print(f"🎬 Spojuji {len(video_clips)} video klipů s rychlými Ken Burns efekty")
        
        try:
            # Spoj video klipy
            final_video = concatenate_videoclips(video_clips)
            
            # Přidej audio stopu k videu
            final_video_with_audio = final_video.with_audio(final_audio)
            
            # Export finálního videa s nízkými FPS pro rychlost
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_filename = f'final_fast_kenburns_with_audio_{timestamp}.mp4'
            output_path = os.path.join(OUTPUT_FOLDER, output_filename)
            
            print(f"⚡ Exportuji rychlé Ken Burns video s audio do {output_path}")
            print(f"📊 Video délka: {final_video.duration:.2f}s, Audio délka: {final_audio.duration:.2f}s")
            
            # Export s audio - nižší FPS pro rychlost
            final_video_with_audio.write_videofile(
                output_path, 
                fps=15,  # Nižší FPS pro rychlost
                codec='libx264',
                audio_codec='aac'
            )
            
            file_size = os.path.getsize(output_path)
            print(f"✅ FINÁLNÍ rychlé Ken Burns VIDEO s audio úspěšně vytvořeno! Velikost: {file_size} bytes")
            
            return jsonify({
                'success': True,
                'message': f'Rychlé Ken Burns video s audio úspěšně vygenerováno',
                'total_videos': 1,
                'successful_clips': len(video_clips),
                'file_size': file_size,
                'filename': output_filename,
                'download_url': f'/api/download/{output_filename}',
                'duration': final_video.duration,
                'audio_duration': final_audio.duration,
                'total_mp3_files': len(narrator_files),
                'duration_per_image': duration_per_image
            })
            
        except Exception as e:
            print(f"❌ CHYBA při exportu rychlého Ken Burns videa s audio: {e}")
            return jsonify({
                'success': False,
                'error': f'Chyba při exportu rychlého Ken Burns videa s audio: {str(e)}',
                'total_videos': 0,
                'successful_clips': len(video_clips)
            }), 500
            
    except Exception as e:
        print(f"❌ KRITICKÁ CHYBA: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'total_videos': 0,
            'successful_clips': 0
        }), 500

def generate_srt_file(narrator_files, project_name, max_mp3_files=0):
    """
    Generuje SRT soubor s perfektně načasovanými titulky
    
    Args:
        narrator_files: Seznam MP3 souborů
        project_name: Název projektu
        max_mp3_files: Maximální počet MP3 souborů (0 = všechny)
    
    Returns:
        str: Cesta k vygenerovanému SRT souboru
    """
    try:
        print(f"📝 Generuji SRT titulky pro projekt: {project_name}")
        
        # Omez počet souborů pokud je specifikováno
        if max_mp3_files > 0:
            narrator_files = narrator_files[:max_mp3_files]
        
        # Načti audio soubory a spočítej jejich délky
        srt_entries = []
        current_time = 0.0
        
        for i, audio_file in enumerate(narrator_files):
            try:
                audio_path = os.path.join(UPLOAD_FOLDER, audio_file)
                audio_clip = AudioFileClip(audio_path)
                
                # SRT časování
                start_time = current_time
                end_time = current_time + audio_clip.duration
                
                # Převod na SRT časový formát (HH:MM:SS,mmm)
                def seconds_to_srt_time(seconds):
                    hours = int(seconds // 3600)
                    minutes = int((seconds % 3600) // 60)
                    secs = int(seconds % 60)
                    millisecs = int((seconds % 1) * 1000)
                    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"
                
                start_srt = seconds_to_srt_time(start_time)
                end_srt = seconds_to_srt_time(end_time)
                
                # Název souboru bez přípony jako text titulků
                subtitle_text = audio_file.replace('.mp3', '').replace('Narrator_', 'Část ')
                
                # SRT formát: číslo, čas, text, prázdný řádek
                srt_entry = f"{i + 1}\n{start_srt} --> {end_srt}\n{subtitle_text}\n"
                srt_entries.append(srt_entry)
                
                current_time = end_time
                print(f"📄 {audio_file}: {start_srt} --> {end_srt} ({audio_clip.duration:.2f}s)")
                
                # Zavři audio clip
                audio_clip.close()
                
            except Exception as e:
                print(f"❌ Chyba při zpracování {audio_file}: {e}")
                continue
        
        # Vytvoř SRT soubor
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        srt_filename = f'{project_name}_subtitles_{timestamp}.srt'
        srt_path = os.path.join(OUTPUT_FOLDER, srt_filename)
        
        with open(srt_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(srt_entries))
        
        print(f"✅ SRT soubor vytvořen: {srt_path}")
        print(f"📊 Celkový počet titulků: {len(srt_entries)}")
        print(f"⏱️ Celková délka: {current_time:.2f}s ({current_time/60:.1f} minut)")
        
        return srt_filename
        
    except Exception as e:
        print(f"❌ Chyba při generování SRT: {e}")
        raise

@app.route('/api/generate-srt', methods=['POST', 'OPTIONS'])
def generate_srt():
    """
    API endpoint pro generování SRT titulků
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response
        
    try:
        data = request.get_json() or {}
        project_name = data.get('project_name', 'video_project')
        max_mp3_files = data.get('max_mp3_files', 0)
        
        # Najdi všechny Narrator MP3 soubory
        narrator_files = []
        for filename in os.listdir(UPLOAD_FOLDER):
            if filename.startswith('Narrator_') and filename.endswith('.mp3'):
                narrator_files.append(filename)
        
        narrator_files.sort()  # Seřadí podle čísel
        print(f"🎵 Nalezeno {len(narrator_files)} Narrator MP3 souborů")
        
        if not narrator_files:
            return jsonify({
                'success': False,
                'error': 'Nebyli nalezeny žádné Narrator MP3 soubory'
            }), 400
        
        # Generuj SRT soubor
        srt_filename = generate_srt_file(narrator_files, project_name, max_mp3_files)
        
        return jsonify({
            'success': True,
            'message': 'SRT titulky úspěšně vygenerovány',
            'filename': srt_filename,
            'download_url': f'/api/download/{srt_filename}',
            'total_subtitles': len(narrator_files) if max_mp3_files <= 0 else min(len(narrator_files), max_mp3_files)
        })
        
    except Exception as e:
        print(f"❌ Chyba při generování SRT: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/download-srt/<filename>')
def download_srt(filename):
    """
    Stažení SRT souboru
    """
    try:
        # Zabezpečení - pouze .srt soubory
        if not filename.endswith('.srt'):
            return jsonify({'error': 'Neplatný typ souboru'}), 400
            
        file_path = os.path.join(OUTPUT_FOLDER, filename)
        if not os.path.exists(file_path):
            return jsonify({'error': 'Soubor nenalezen'}), 404
            
        return send_file(file_path, as_attachment=True, download_name=filename)
        
    except Exception as e:
        print(f"❌ Chyba při stahování SRT: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate-video-structure', methods=['POST', 'OPTIONS'])
def generate_video_structure():
    """
    Generuje strukturu videa pomocí OpenAI API
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response
        
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'Žádná data nebyla poslána'
            }), 400
            
        topic = data.get('topic', '')
        target_minutes = data.get('target_minutes', 10)
        target_words = data.get('target_words', 1500)
        assistant_category = data.get('assistant_category', 'general')
        
        print(f"🤖 STRUKTURA: Generuji strukturu pro téma: {topic}")
        print(f"📊 Cíl: {target_minutes} minut, {target_words} slov")
        print(f"🏷️ Kategorie: {assistant_category}")
        
        if not topic:
            return jsonify({
                'success': False,
                'error': 'Téma videa není specifikováno'
            }), 400
        
        # Vytvoř prompt pro generování struktury videa
        prompt = f"""
        Vytvoř strukturu pro dokumentární video na téma: "{topic}"
        
        Požadavky:
        - Délka: {target_minutes} minut 
        - Počet slov: přibližně {target_words}
        - Kategorie: {assistant_category}
        - Styl: Profesionální dokumentární narrace
        
        Struktura by měla obsahovat:
        1. Úvod (cca 10% délky)
        2. Hlavní část rozdělená do 3-5 segmentů
        3. Závěr (cca 10% délky)
        
        Vrať odpověď jako JSON s touto PŘESNOU strukturou:
        {{
            "title": "Název videa",
            "total_duration_minutes": {target_minutes},
            "estimated_words": {target_words},
            "segments": [
                {{
                    "id": "segment_1",
                    "title": "Název segmentu",
                    "duration_minutes": 2,
                    "content": "Popis obsahu segmentu",
                    "key_points": ["Klíčový bod 1", "Klíčový bod 2"]
                }},
                {{
                    "id": "segment_2", 
                    "title": "Název segmentu 2",
                    "duration_minutes": 2,
                    "content": "Popis obsahu segmentu 2",
                    "key_points": ["Klíčový bod 3", "Klíčový bod 4"]
                }}
            ]
        }}
        
        DŮLEŽITÉ: Každý segment MUSÍ mít pole "id" ve formátu "segment_X".
        """
        
        # Volej OpenAI API
        result = call_openai(prompt, model="gpt-4o")
        
        if result.get('success'):
            print(f"✅ STRUKTURA: Úspěšně vygenerována struktura videa")
            
            # Frontend očekává strukturu s detail_assistant_id
            structure_data = result['data']
            print(f"🔍 DEBUG: Struktura z OpenAI: {structure_data}")
            
            structure_data['detail_assistant_id'] = data.get('detail_assistant_id')
            structure_data['video_context'] = {
                'topic': topic,
                'target_minutes': target_minutes,
                'assistant_category': assistant_category
            }
            
            print(f"🔍 DEBUG: Finální struktura pro frontend: {structure_data}")
            
            return jsonify({
                'success': True,
                'data': structure_data,  # Frontend očekává 'data' místo 'structure'
                'message': 'Struktura videa úspěšně vygenerována'
            })
        else:
            print(f"❌ STRUKTURA: Chyba při generování: {result.get('error')}")
            return jsonify({
                'success': False,
                'error': result.get('error', 'Neznámá chyba při generování struktury')
            }), 500
            
    except Exception as e:
        print(f"❌ STRUKTURA: Kritická chyba: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/script/generate', methods=['POST', 'OPTIONS'])
def script_generate():
    """
    Spustí 4-step Script pipeline:
    Research -> Narrative -> Validation -> Composer (deterministic)
    Perzistence: projects/<episode_id>/script_state.json
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response

    try:
        data = request.get_json() or {}
        topic = (data.get('topic') or '').strip()
        language = (data.get('language') or '').strip()
        target_minutes = data.get('target_minutes')
        channel_profile = data.get('channel_profile')
        research_config = data.get('research_config')
        narrative_config = data.get('narrative_config')
        validator_config = data.get('validator_config')
        tts_format_config = data.get('tts_format_config')
        footage_director_config = data.get('footage_director_config')

        if not topic:
            return jsonify({'success': False, 'error': 'topic je povinné'}), 400
        if not language:
            return jsonify({'success': False, 'error': 'language je povinné'}), 400

        # Provider API keys (server-side only)
        provider_api_keys = {
            'openai': (os.getenv('OPENAI_API_KEY') or '').strip(),
            'openrouter': (os.getenv('OPENROUTER_API_KEY') or '').strip()
        }

        # Validate required providers based on configs
        # AUTO-DETECT: If no provider specified, use OpenRouter if available (otherwise OpenAI)
        default_provider = 'openrouter' if provider_api_keys.get('openrouter') else 'openai'
        
        def _provider_from(cfg):
            if isinstance(cfg, dict):
                return str(cfg.get('provider') or default_provider).strip().lower()
            return default_provider

        providers_used = {
            _provider_from(research_config),
            _provider_from(narrative_config),
            _provider_from(validator_config),
            _provider_from(tts_format_config),
            _provider_from(footage_director_config),
        }
        for prov in providers_used:
            if prov not in ('openai', 'openrouter'):
                return jsonify({'success': False, 'error': f'Nepodporovaný provider: {prov}'}), 400
            if not provider_api_keys.get(prov):
                return jsonify({'success': False, 'error': f'Chybí API key na serveru pro provider: {prov}'}), 400

        # Normalize target_minutes if provided
        if target_minutes is not None:
            try:
                target_minutes = int(target_minutes)
            except Exception:
                return jsonify({'success': False, 'error': 'target_minutes musí být číslo'}), 400

        try:
            episode_id = script_pipeline_service.start_pipeline_async(
                topic=topic,
                language=language,
                target_minutes=target_minutes,
                channel_profile=channel_profile,
                provider_api_keys=provider_api_keys,
                research_config=research_config if isinstance(research_config, dict) else None,
                narrative_config=narrative_config if isinstance(narrative_config, dict) else None,
                validator_config=validator_config if isinstance(validator_config, dict) else None,
                tts_format_config=tts_format_config if isinstance(tts_format_config, dict) else None,
                footage_director_config=footage_director_config if isinstance(footage_director_config, dict) else None,
            )
        except RuntimeError as e:
            msg = str(e)
            if msg.startswith("PIPELINE_BUSY:"):
                # UI-friendly: return success=false without creating an ERROR episode.
                return jsonify({"success": False, "error": msg.replace("PIPELINE_BUSY:", "").strip()}), 200
            raise

        return jsonify({'success': True, 'episode_id': episode_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/script/state/<episode_id>', methods=['GET'])
def script_state(episode_id):
    """
    Vrátí script_state.json pro dané episode_id (source of truth pro reload UI)
    """
    try:
        state = project_store.read_script_state(episode_id)
        return jsonify({'success': True, 'data': state})
    except FileNotFoundError:
        return jsonify({'success': False, 'error': 'episode_id nenalezen'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/video/generate-aar-queries/<episode_id>', methods=['POST', 'OPTIONS'])
def generate_aar_queries(episode_id):
    """
    AUTO-GENERATE AAR queries from shot_plan (BEFORE Preview).
    
    This endpoint is called AUTOMATICALLY after FDA completion.
    It generates episode-level queries and saves them to archive_manifest.json
    WITHOUT performing any search.
    
    Returns:
        {
            "success": True,
            "episode_id": str,
            "queries": [str],  # Generated AAR queries
            "query_count": int
        }
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST,OPTIONS')
        return response
    
    try:
        from archive_asset_resolver import _extract_episode_queries
        
        episode_id = (episode_id or '').strip()
        if not episode_id:
            return jsonify({'success': False, 'error': 'episode_id je povinné'}), 400
        
        # Load state
        state = project_store.read_script_state(episode_id)
        if not isinstance(state, dict):
            return jsonify({'success': False, 'error': 'episode_id nenalezen'}), 404
        
        # Extract shot_plan
        shot_plan = None
        if isinstance(state.get("metadata"), dict) and isinstance(state["metadata"].get("shot_plan"), dict):
            shot_plan = state["metadata"]["shot_plan"]
        elif isinstance(state.get("shot_plan"), dict):
            shot_plan = state["shot_plan"]
        
        if not shot_plan:
            return jsonify({
                'success': False,
                'error': 'Shot plan nenalezen. Nejdříve spusť FDA (Footage Director).'
            }), 400
        
        # Extract scenes
        scenes = []
        if isinstance(shot_plan.get("scenes"), list):
            scenes = shot_plan["scenes"]
        elif isinstance(shot_plan.get("shot_plan"), dict) and isinstance(shot_plan["shot_plan"].get("scenes"), list):
            scenes = shot_plan["shot_plan"]["scenes"]
        
        if not scenes:
            return jsonify({
                'success': False,
                'error': 'Shot plan nemá žádné scény'
            }), 400
        
        # Get episode topic (for context)
        episode_topic = state.get("topic") or state.get("metadata", {}).get("topic") or ""
        
        # Generate queries (NO SEARCH - just generation!)
        print(f"🎯 Generating AAR queries for episode: {episode_id}")
        episode_queries = _extract_episode_queries(scenes, max_queries=12, episode_topic=episode_topic)
        print(f"📝 Generated {len(episode_queries)} AAR queries: {episode_queries}")
        
        # Save queries to archive_manifest.json (or create minimal manifest)
        episode_dir = project_store.episode_dir(episode_id)
        manifest_path = os.path.join(episode_dir, 'archive_manifest.json')
        
        # Load or create manifest
        manifest = {}
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
            except Exception:
                manifest = {}
        
        # Update episode_pool section (preserve existing data)
        if 'episode_pool' not in manifest:
            manifest['episode_pool'] = {}
        
        manifest['episode_pool']['queries_used'] = episode_queries
        manifest['episode_pool']['queries_generated_at'] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        manifest['episode_pool']['mode'] = 'episode_first'
        
        # Save manifest
        os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        
        print(f"✅ AAR queries saved to {manifest_path}")
        
        return jsonify({
            'success': True,
            'episode_id': episode_id,
            'queries': episode_queries,
            'query_count': len(episode_queries),
            'manifest_path': manifest_path
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }), 500


@app.route('/api/video/search-queries/<episode_id>', methods=['GET', 'POST', 'DELETE', 'OPTIONS'])
def video_search_queries(episode_id):
    """
    UI helper: allow users to inspect and edit search queries used by AAR.
    
    Stores user additions in script_state.json under: user_search_queries: [str, ...]
    AAR will treat these as high-priority queries by prepending them to each scene.search_queries.
    
    Methods:
    - GET: returns { auto_queries, user_queries, combined_queries }
    - POST: body { query: str } or { queries: [str] } (replace)
    - DELETE: body { query: str } (remove)
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'GET,POST,DELETE,OPTIONS')
        return response

    try:
        episode_id = (episode_id or '').strip()
        if not episode_id:
            return jsonify({'success': False, 'error': 'episode_id je povinné'}), 400

        # Load state
        state = project_store.read_script_state(episode_id)
        if not isinstance(state, dict):
            state = {}

        def _norm(q: str) -> str:
            q = (q or '').strip()
            # collapse internal whitespace
            q = ' '.join(q.split())
            return q

        def _dedupe_keep_order(items):
            seen = set()
            out = []
            for x in items:
                if not isinstance(x, str):
                    continue
                nx = _norm(x)
                if not nx:
                    continue
                key = nx.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append(nx)
            return out

        user_queries = state.get("user_search_queries")
        user_queries = user_queries if isinstance(user_queries, list) else []
        user_queries = _dedupe_keep_order(user_queries)
        
        # Deprecated: FDA auto queries are no longer used/exposed.
        excluded_auto: list = []
        excluded_auto_lower = set()

        def _load_episode_pool_queries() -> list:
            """
            Load AAR-generated episode pool queries from archive_manifest.json.
            Returns a deduped list (may be empty). Never throws.
            """
            try:
                episode_dir = project_store.episode_dir(episode_id)
                manifest_path = os.path.join(episode_dir, "archive_manifest.json")
                if not os.path.exists(manifest_path):
                    return []
                import json as json_lib
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json_lib.load(f) or {}
                pool_meta = manifest.get("episode_pool") or {}
                raw_queries = pool_meta.get("queries_used") or []
                return _dedupe_keep_order([str(q) for q in raw_queries if isinstance(q, str)])
            except Exception:
                return []

        if request.method == 'GET':
            episode_pool_queries = _load_episode_pool_queries()

            # Auto-generate AAR queries on-demand (NO SEARCH) when missing.
            # This fixes UX: user can see/edit queries right after FDA without running Preview.
            if not episode_pool_queries:
                try:
                    from archive_asset_resolver import _extract_episode_queries
                    md = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
                    shot_plan = None
                    if isinstance(md.get("shot_plan"), dict):
                        shot_plan = md.get("shot_plan")
                    elif isinstance(state.get("shot_plan"), dict):
                        shot_plan = state.get("shot_plan")

                    scenes = []
                    if isinstance(shot_plan, dict) and isinstance(shot_plan.get("scenes"), list):
                        scenes = shot_plan.get("scenes") or []
                    elif (
                        isinstance(shot_plan, dict)
                        and isinstance(shot_plan.get("shot_plan"), dict)
                        and isinstance(shot_plan["shot_plan"].get("scenes"), list)
                    ):
                        scenes = shot_plan["shot_plan"].get("scenes") or []

                    if scenes:
                        episode_topic = state.get("topic") or (md.get("topic") if isinstance(md, dict) else "") or ""
                        generated = _extract_episode_queries(scenes, max_queries=12, episode_topic=episode_topic)
                        generated = _dedupe_keep_order([str(q) for q in generated if isinstance(q, str)])
                        if generated:
                            # Persist to manifest so the UI (and later AAR runs) sees stable queries.
                            episode_dir = project_store.episode_dir(episode_id)
                            manifest_path = os.path.join(episode_dir, 'archive_manifest.json')
                            manifest = {}
                            try:
                                if os.path.exists(manifest_path):
                                    import json as json_lib
                                    with open(manifest_path, 'r', encoding='utf-8') as f:
                                        manifest = json_lib.load(f) or {}
                            except Exception:
                                manifest = {}
                            if not isinstance(manifest, dict):
                                manifest = {}
                            if not isinstance(manifest.get("episode_pool"), dict):
                                manifest["episode_pool"] = {}
                            manifest["episode_pool"]["mode"] = "episode_first"
                            manifest["episode_pool"]["queries_used"] = generated
                            manifest["episode_pool"]["queries_generated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                            os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
                            import json as json_lib
                            with open(manifest_path, 'w', encoding='utf-8') as f:
                                json_lib.dump(manifest, f, ensure_ascii=False, indent=2)
                            episode_pool_queries = generated
                except Exception:
                    # Non-fatal: user can still click the explicit generate button or run Preview.
                    pass

            # Combined: what will actually be used by AAR search (user overrides first).
            combined = _dedupe_keep_order(user_queries + (episode_pool_queries or []))
            
            return jsonify({
                'success': True,
                'episode_id': episode_id,
                'auto_queries': [],  # DEPRECATED: FDA queries no longer used (AAR is sole source)
                'user_queries': user_queries,
                'excluded_auto_queries': excluded_auto,
                'combined_queries': combined,
                'episode_pool_queries': episode_pool_queries,
            })

        data = request.get_json() or {}
        if request.method == 'POST':
            # Replace
            if isinstance(data.get("queries"), list):
                new_q = _dedupe_keep_order(data.get("queries"))
                state["user_search_queries"] = new_q
                project_store.write_script_state(episode_id, state)
                episode_pool_queries = _load_episode_pool_queries()
                combined = _dedupe_keep_order(new_q + (episode_pool_queries or []))
                return jsonify({
                    'success': True,
                    'episode_id': episode_id,
                    'user_queries': new_q,
                    'auto_queries': [],  # deprecated
                    'combined_queries': combined,
                    'episode_pool_queries': episode_pool_queries,
                })

            # Add single
            q = data.get("query")
            if not isinstance(q, str):
                return jsonify({'success': False, 'error': 'query musí být string'}), 400
            qn = _norm(q)
            if not qn:
                return jsonify({'success': False, 'error': 'query je prázdné'}), 400
            # Basic guardrail
            if len(qn) > 160:
                return jsonify({'success': False, 'error': 'query je příliš dlouhé (max 160 znaků)'}), 400

            merged = _dedupe_keep_order(user_queries + [qn])
            state["user_search_queries"] = merged
            project_store.write_script_state(episode_id, state)
            episode_pool_queries = _load_episode_pool_queries()
            combined = _dedupe_keep_order(merged + (episode_pool_queries or []))
            return jsonify({
                'success': True,
                'episode_id': episode_id,
                'user_queries': merged,
                'auto_queries': [],  # deprecated
                'combined_queries': combined,
                'episode_pool_queries': episode_pool_queries,
            })

        if request.method == 'DELETE':
            q = data.get("query")
            if not isinstance(q, str):
                return jsonify({'success': False, 'error': 'query musí být string'}), 400
            qn = _norm(q)
            if not qn:
                return jsonify({'success': False, 'error': 'query je prázdné'}), 400
            
            target = qn.lower()
            is_user_query = any(x.lower() == target for x in user_queries)
            
            if is_user_query:
                # Remove from user_queries
                kept = [x for x in user_queries if x.lower() != target]
                state["user_search_queries"] = kept
                user_queries = kept
            else:
                # AAR queries are not editable here; user can only add/remove their own overrides.
                return jsonify({
                    'success': False,
                    'error': 'Lze mazat pouze vlastní dotazy (AAR dotazy jsou generované a nelze je mazat zde).'
                }), 400
            
            project_store.write_script_state(episode_id, state)
            
            episode_pool_queries = _load_episode_pool_queries()
            combined = _dedupe_keep_order(user_queries + (episode_pool_queries or []))
            
            return jsonify({
                'success': True,
                'episode_id': episode_id,
                'user_queries': user_queries,
                'auto_queries': [],  # deprecated
                'excluded_auto_queries': [],
                'combined_queries': combined,
                'episode_pool_queries': episode_pool_queries,
            })

        return jsonify({'success': False, 'error': 'Unsupported method'}), 405
    except FileNotFoundError:
        return jsonify({'success': False, 'error': 'episode_id nenalezen'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/projects/<episode_id>', methods=['GET'])
def get_project_details(episode_id):
    """
    Vrátí detaily projektu včetně seznamu MP3 souborů
    """
    try:
        episode_dir = project_store.episode_dir(episode_id)

        # Preferuj per-episode voiceover (projects/<ep>/voiceover/*.mp3)
        voiceover_dir = os.path.join(episode_dir, "voiceover")
        mp3_files = []

        # Pokud existuje state a obsahuje seznam vygenerovaných souborů, použij ho jako source of truth
        try:
            state = project_store.read_script_state(episode_id)
        except Exception:
            state = None

        tts_generated_files = []
        tts_generated_dir = None
        if isinstance(state, dict):
            tts_generated_files = state.get("tts_generated_files") or []
            tts_generated_dir = state.get("tts_generated_dir")

        if tts_generated_files and isinstance(tts_generated_files, list):
            # Zkompiluj metadata ze souborů (preferuj voiceover endpoint, pokud je v per-episode složce)
            for fname in tts_generated_files:
                if not isinstance(fname, str):
                    continue
                # Bezpečnost – jen basename
                safe_name = secure_filename(fname)
                # Resolve path
                base_dir = tts_generated_dir if (isinstance(tts_generated_dir, str) and tts_generated_dir) else voiceover_dir
                candidate_path = os.path.join(base_dir, safe_name)
                if os.path.exists(candidate_path):
                    mp3_files.append({
                        "filename": safe_name,
                        "size": os.path.getsize(candidate_path),
                        "url": f"/api/projects/{episode_id}/audio/{safe_name}",
                    })
        else:
            # Fallback: scan per-episode voiceover dir
            if os.path.exists(voiceover_dir):
                for file in os.listdir(voiceover_dir):
                    if file.endswith(".mp3"):
                        mp3_path = os.path.join(voiceover_dir, file)
                        mp3_files.append({
                            "filename": file,
                            "size": os.path.getsize(mp3_path),
                            "url": f"/api/projects/{episode_id}/audio/{file}",
                        })

        # Migration helper (legacy): pokud per-episode voiceover neexistuje,
        # ale v uploads/ jsou Narrator_*.mp3 a počet odpovídá narration_blocks, zkopíruj do voiceover_dir.
        if not mp3_files and isinstance(state, dict) and state.get("tts_ready_package"):
            try:
                expected = len(state.get("tts_ready_package", {}).get("narration_blocks", []) or [])
                legacy = sorted([
                    f for f in os.listdir(UPLOAD_FOLDER)
                    if f.startswith("Narrator_") and f.endswith(".mp3")
                ])
                if expected > 0 and len(legacy) == expected:
                    os.makedirs(voiceover_dir, exist_ok=True)
                    import shutil
                    migrated = []
                    for f in legacy:
                        src = os.path.join(UPLOAD_FOLDER, f)
                        dst = os.path.join(voiceover_dir, f)
                        shutil.copy2(src, dst)
                        migrated.append(f)
                    # persist to state
                    state["tts_generated_files"] = migrated
                    state["tts_generated_dir"] = voiceover_dir
                    state["tts_generated_count"] = len(migrated)
                    project_store.write_script_state(episode_id, state)

                    mp3_files = [{
                        "filename": f,
                        "size": os.path.getsize(os.path.join(voiceover_dir, f)),
                        "url": f"/api/projects/{episode_id}/audio/{f}",
                    } for f in migrated]
            except Exception as e:
                print(f"⚠️  /api/projects: legacy voiceover migration failed: {e}")

        mp3_files.sort(key=lambda x: x.get("filename", ""))
        
        return jsonify({
            'success': True,
            'episode_id': episode_id,
            'mp3_files': mp3_files,
            'mp3_count': len(mp3_files),
            'has_voiceover': len(mp3_files) > 0
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/projects/<episode_id>/audio/<filename>', methods=['GET'])
def get_project_audio_file(episode_id, filename):
    """
    Bezpečný endpoint pro přehrání/stažení voiceover MP3 uložených per-episode.
    """
    try:
        safe_name = secure_filename(filename)
        episode_dir = project_store.episode_dir(episode_id)
        voiceover_dir = os.path.join(episode_dir, "voiceover")
        file_path = os.path.join(voiceover_dir, safe_name)
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'error': 'Audio soubor nebyl nalezen'}), 404
        return send_file(file_path, as_attachment=False, mimetype="audio/mpeg")
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/projects/<episode_id>/music', methods=['GET'])
def get_project_music(episode_id):
    """
    Per-episode Background Music list (stored locally in projects/<ep>/assets/music/).
    """
    try:
        episode_id = (episode_id or '').strip()
        if not episode_id:
            return jsonify({'success': False, 'error': 'episode_id je povinné'}), 400

        episode_dir = project_store.episode_dir(episode_id)
        if not os.path.exists(episode_dir):
            return jsonify({'success': False, 'error': 'episode_id nenalezen'}), 404

        manifest = load_music_manifest(episode_dir)
        tracks = manifest.get("tracks") or []
        # Add helpful file existence flags
        for t in tracks:
            if not isinstance(t, dict):
                continue
            fn = secure_filename(t.get("filename") or "")
            t["exists"] = os.path.exists(os.path.join(music_dir_for_episode(episode_dir), fn))

        return jsonify({'success': True, 'episode_id': episode_id, 'music': tracks})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/projects/<episode_id>/music/upload', methods=['POST', 'OPTIONS'])
def upload_project_music(episode_id):
    """
    Upload 1..N music files (mp3/wav) into projects/<ep>/assets/music/ as user_music_XX.ext.
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response

    try:
        episode_id = (episode_id or '').strip()
        if not episode_id:
            return jsonify({'success': False, 'error': 'episode_id je povinné'}), 400

        episode_dir = project_store.episode_dir(episode_id)
        if not os.path.exists(episode_dir):
            return jsonify({'success': False, 'error': 'episode_id nenalezen'}), 404

        files = request.files.getlist('music_files')
        if not files:
            # allow single file field name fallback
            one = request.files.get('music_file')
            files = [one] if one else []
        if not files:
            # very common generic field name
            one = request.files.get('file')
            files = [one] if one else []

        if not files:
            return jsonify({'success': False, 'error': 'Chybí music_files (multipart)'}), 400

        # Validate extensions + size (MVP)
        allowed_ext = ('.mp3', '.wav')
        max_bytes = 100 * 1024 * 1024  # 100MB per file
        valid = []
        for f in files:
            if not f:
                continue
            name = secure_filename(getattr(f, 'filename', '') or '')
            if not name.lower().endswith(allowed_ext):
                continue
            try:
                # werkzeug FileStorage may not have content_length reliably; attempt best effort
                if getattr(f, 'content_length', None) and int(f.content_length) > max_bytes:
                    continue
            except Exception:
                pass
            valid.append(f)

        if not valid:
            return jsonify({'success': False, 'error': 'Nepovolený typ souboru. Povolené: MP3, WAV'}), 400

        added, manifest = add_music_files(episode_dir, valid)
        return jsonify({'success': True, 'episode_id': episode_id, 'added': added, 'music': manifest.get('tracks', [])})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/projects/<episode_id>/music/update', methods=['POST'])
def update_project_music(episode_id):
    """
    Update music track metadata (active/tag).
    Body: { filename: str, active?: bool, tag?: str }
    """
    try:
        episode_id = (episode_id or '').strip()
        if not episode_id:
            return jsonify({'success': False, 'error': 'episode_id je povinné'}), 400

        episode_dir = project_store.episode_dir(episode_id)
        if not os.path.exists(episode_dir):
            return jsonify({'success': False, 'error': 'episode_id nenalezen'}), 404

        data = request.get_json() or {}
        filename = secure_filename((data.get('filename') or '').strip())
        if not filename:
            return jsonify({'success': False, 'error': 'filename je povinné'}), 400

        active = data.get('active', None)
        tag = data.get('tag', None) if 'tag' in data else None

        manifest = update_music_track(episode_dir, filename=filename, active=active if active is None else bool(active), tag=tag)
        return jsonify({'success': True, 'episode_id': episode_id, 'music': manifest.get('tracks', [])})
    except FileNotFoundError as e:
        return jsonify({'success': False, 'error': str(e)}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ========================================
# GLOBAL MUSIC LIBRARY API
# ========================================

@app.route('/api/music/library', methods=['GET'])
def get_global_music_library():
    """
    GET global music library (všechny uložené tracky).
    """
    try:
        manifest = load_global_music_manifest()
        tracks = manifest.get("tracks") or []
        
        # Add file existence flags
        for t in tracks:
            if not isinstance(t, dict):
                continue
            fn = secure_filename(t.get("filename") or "")
            file_path = get_music_file_path(fn)
            t["exists"] = file_path is not None and os.path.exists(file_path)

        # Sort: newest first (uploaded_at desc)
        def _ts(x):
            try:
                return (x or "").strip()
            except Exception:
                return ""

        tracks_sorted = [t for t in tracks if isinstance(t, dict)]
        tracks_sorted.sort(key=lambda t: _ts(t.get("uploaded_at")), reverse=True)

        return jsonify({'success': True, 'tracks': tracks_sorted, 'total': len(tracks_sorted)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/music/library/upload', methods=['POST', 'OPTIONS'])
def upload_to_global_music_library():
    """
    Upload 1..N music files do globální knihovny.
    Body (multipart/form-data):
    - music_files: file(s)
    - tags: JSON array of strings (optional)
    - mood: string (optional)
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response

    try:
        files = request.files.getlist('music_files')
        if not files:
            one = request.files.get('music_file')
            files = [one] if one else []
        if not files:
            one = request.files.get('file')
            files = [one] if one else []

        if not files:
            return jsonify({'success': False, 'error': 'Chybí music_files (multipart)'}), 400

        # Parse optional metadata
        tags_str = request.form.get('tags', '[]')
        try:
            tags = json.loads(tags_str) if tags_str else []
        except Exception:
            tags = []
        
        mood = request.form.get('mood', 'neutral')

        # Validate extensions + size
        allowed_ext = ('.mp3', '.wav')
        max_bytes = 100 * 1024 * 1024  # 100MB
        valid = []
        for f in files:
            if not f:
                continue
            name = secure_filename(getattr(f, 'filename', '') or '')
            if not name.lower().endswith(allowed_ext):
                continue
            try:
                if getattr(f, 'content_length', None) and int(f.content_length) > max_bytes:
                    continue
            except Exception:
                pass
            valid.append(f)

        if not valid:
            return jsonify({'success': False, 'error': 'Nepovolený typ souboru. Povolené: MP3, WAV'}), 400

        added, manifest = add_global_music_files(valid, tags=tags, mood=mood)
        return jsonify({
            'success': True,
            'added': added,
            'tracks': manifest.get('tracks', []),
            'total': len(manifest.get('tracks', []))
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/music/library/update', methods=['POST'])
def update_global_music_track_api():
    """
    Update global music track metadata.
    Body: { filename: str, active?: bool, tags?: string[], mood?: str }
    """
    try:
        data = request.get_json() or {}
        filename = secure_filename((data.get('filename') or '').strip())
        if not filename:
            return jsonify({'success': False, 'error': 'filename je povinné'}), 400

        active = data.get('active', None)
        tags = data.get('tags', None)
        mood = data.get('mood', None)

        manifest = update_global_music_track(
            filename=filename,
            active=active if active is None else bool(active),
            tags=tags,
            mood=mood
        )
        
        return jsonify({'success': True, 'tracks': manifest.get('tracks', [])})
    except FileNotFoundError as e:
        return jsonify({'success': False, 'error': str(e)}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/music/library/delete', methods=['POST'])
def delete_global_music_track_api():
    """
    Delete global music track (soubor + metadata).
    Body: { filename: str }
    """
    try:
        data = request.get_json() or {}
        filename = secure_filename((data.get('filename') or '').strip())
        if not filename:
            return jsonify({'success': False, 'error': 'filename je povinné'}), 400

        manifest = delete_global_music_track(filename)
        return jsonify({'success': True, 'tracks': manifest.get('tracks', [])})
    except FileNotFoundError as e:
        return jsonify({'success': False, 'error': str(e)}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/music/library/select-auto', methods=['POST'])
def select_music_auto_api():
    """
    Automatický výběr hudby podle kontextu.
    Body: {
        preferred_mood?: str,
        preferred_tags?: string[],
        min_duration_sec?: float,
        context?: object
    }
    Returns: { success: bool, selected_track?: object }
    """
    try:
        data = request.get_json() or {}
        
        selected = select_music_auto(
            context=data.get('context'),
            preferred_mood=data.get('preferred_mood'),
            preferred_tags=data.get('preferred_tags'),
            min_duration_sec=data.get('min_duration_sec')
        )
        
        if selected:
            return jsonify({'success': True, 'selected_track': selected})
        else:
            return jsonify({'success': False, 'error': 'Žádná hudba nevyhovuje kritériím'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/music/library/download/<filename>', methods=['GET'])
def download_global_music(filename):
    """
    Download music soubor z global library.
    """
    try:
        safe_name = secure_filename(filename or '')
        if not safe_name:
            return jsonify({'success': False, 'error': 'Invalid filename'}), 400
        
        file_path = get_music_file_path(safe_name)
        if not file_path or not os.path.exists(file_path):
            return jsonify({'success': False, 'error': 'Music file not found'}), 404
        
        return send_file(file_path, as_attachment=False, mimetype="audio/mpeg")
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/projects/<episode_id>/music/select-global', methods=['POST'])
def select_global_music_for_episode(episode_id):
    """
    Uloží selected_global_music do script_state pro daný episode.
    Body: { selected_track: object | null }
    """
    try:
        episode_id = (episode_id or '').strip()
        if not episode_id:
            return jsonify({'success': False, 'error': 'episode_id je povinné'}), 400

        episode_dir = project_store.episode_dir(episode_id)
        if not os.path.exists(episode_dir):
            return jsonify({'success': False, 'error': 'episode_id nenalezen'}), 404

        data = request.get_json() or {}
        selected_track = data.get('selected_track')

        # Load current script_state
        state = project_store.read_script_state(episode_id)
        
        # Update selected_global_music
        state['selected_global_music'] = selected_track
        
        # Save
        project_store.write_script_state(episode_id, state)

        return jsonify({'success': True, 'episode_id': episode_id, 'selected_music': selected_track})
    except FileNotFoundError:
        return jsonify({'success': False, 'error': 'Script state nenalezen'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/script/reset-lock', methods=['POST'])
def reset_script_lock():
    """
    Resetuje lock pro script pipeline, pokud žádný step neběží.
    Používá se při resetu UI - uvolní lock, aby bylo možné začít nový běh.
    """
    try:
        # Zkontroluj, zda nějaký step běží
        unlocked = script_pipeline_service._check_and_force_unlock_if_no_running_steps()
        
        if unlocked:
            return jsonify({'success': True, 'message': 'Lock byl uvolněn (žádný step neběžel)'})
        else:
            # Zkusíme force unlock i když nějaký step může běžet (stale lock)
            force_unlocked = script_pipeline_service._force_unlock_if_stale(max_age_seconds=300)  # 5 minut
            if force_unlocked:
                return jsonify({'success': True, 'message': 'Stale lock byl uvolněn'})
            else:
                return jsonify({
                    'success': False,
                    'error': 'Lock nelze uvolnit - pravděpodobně nějaký step stále běží nebo lock je čerstvý'
                }), 409
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/script/retry-step', methods=['POST'])
def retry_step():
    """
    Retry a single step (research, narrative, validation, composer, tts_format).
    - default: ERROR steps
    - validation: also allowed when DONE but ValidationResult.status=FAIL
    - narrative: also allowed when DONE but ValidationResult.status=FAIL and attempts.narrative < 2
    Body: { episode_id: str, step: str }
    """
    try:
        data = request.get_json() or {}
        episode_id = (data.get('episode_id') or '').strip()
        step = (data.get('step') or '').strip()

        if not episode_id or not step:
            return jsonify({'success': False, 'error': 'episode_id a step jsou povinné'}), 400

        allowed = (
            'research',
            'narrative',
            'validation',
            'composer',
            'tts_format',
            'footage_director',
            'asset_resolver',
            'compilation_builder',
        )
        if step not in allowed:
            return jsonify({'success': False, 'error': f"step musí být: {', '.join(allowed)}"}), 400

        # Provider API keys
        provider_api_keys = {
            'openai': os.getenv('OPENAI_API_KEY') or '',
            'openrouter': os.getenv('OPENROUTER_API_KEY') or '',
        }

        success = script_pipeline_service.retry_step_async(episode_id, step, provider_api_keys)
        if not success:
            return jsonify({'success': False, 'error': f'Retry pro krok {step} nelze (nesplněné podmínky)'}), 400

        return jsonify({'success': True, 'message': f'Retry {step} spuštěn'})
    except FileNotFoundError:
        return jsonify({'success': False, 'error': 'episode_id nenalezen'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/script/config/<episode_id>/footage_director', methods=['POST'])
def update_episode_footage_director_config(episode_id):
    """
    Update per-episode Footage Director (FDA) config, so users can switch provider/model without regenerating steps 1-5.
    Body: { provider: "openai"|"openrouter", model?: str, temperature?: number, prompt_template?: string|null }
    """
    try:
        episode_id = (episode_id or '').strip()
        if not episode_id:
            return jsonify({'success': False, 'error': 'episode_id je povinné'}), 400

        # Load state
        state = project_store.read_script_state(episode_id)

        data = request.get_json() or {}
        provider = (data.get('provider') or '').strip().lower()
        if provider not in ('openai', 'openrouter'):
            return jsonify({'success': False, 'error': 'provider musí být openai nebo openrouter'}), 400

        cfg = state.get('footage_director_config') or {}
        cfg['provider'] = provider
        if 'model' in data and data.get('model') is not None:
            cfg['model'] = str(data.get('model')).strip()
        if 'temperature' in data and data.get('temperature') is not None:
            try:
                cfg['temperature'] = float(data.get('temperature'))
            except Exception:
                return jsonify({'success': False, 'error': 'temperature musí být číslo'}), 400
        if 'prompt_template' in data:
            pt = data.get('prompt_template')
            cfg['prompt_template'] = (str(pt) if pt is not None else None)

        cfg['step'] = 'footage_director'
        state['footage_director_config'] = cfg
        project_store.write_script_state(episode_id, state)

        return jsonify({'success': True, 'episode_id': episode_id, 'footage_director_config': cfg})
    except FileNotFoundError:
        return jsonify({'success': False, 'error': 'episode_id nenalezen'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/script/retry/narrative/<episode_id>', methods=['POST'])
def retry_narrative_apply_patch(episode_id):
    """
    Narrative retry for Validation FAIL:
    - Uses existing research_report
    - Uses latest validation_result.patch_instructions
    - Runs Writing once (apply patch) -> Validation -> if PASS then Composer
    """
    try:
        episode_id = (episode_id or '').strip()
        if not episode_id:
            return jsonify({'success': False, 'error': 'episode_id je povinné'}), 400

        provider_api_keys = {
            'openai': os.getenv('OPENAI_API_KEY') or '',
            'openrouter': os.getenv('OPENROUTER_API_KEY') or '',
        }

        ok = script_pipeline_service.retry_narrative_apply_patch_async(episode_id, provider_api_keys)
        if not ok:
            return jsonify({'success': False, 'error': 'Retry writing není povolen (vyčerpán limit pokusů nebo chybí FAIL+patch)'}), 400

        return jsonify({'success': True, 'message': 'Retry writing (apply patch) spuštěn'})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except FileNotFoundError:
        return jsonify({'success': False, 'error': 'episode_id nenalezen'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/script/retry/validation/<episode_id>', methods=['POST'])
def retry_validation_only(episode_id):
    """
    Validation-only retry:
    - Re-runs Validation on current draft_script
    - If PASS then Composer
    """
    try:
        episode_id = (episode_id or '').strip()
        if not episode_id:
            return jsonify({'success': False, 'error': 'episode_id je povinné'}), 400

        provider_api_keys = {
            'openai': os.getenv('OPENAI_API_KEY') or '',
            'openrouter': os.getenv('OPENROUTER_API_KEY') or '',
        }

        ok = script_pipeline_service.retry_validation_only_async(episode_id, provider_api_keys)
        if not ok:
            return jsonify({'success': False, 'error': 'Retry validation není možné (chybí draft_script nebo kontext)'}), 400

        return jsonify({'success': True, 'message': 'Retry validation spuštěn'})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except FileNotFoundError:
        return jsonify({'success': False, 'error': 'episode_id nenalezen'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/fda/generate', methods=['POST', 'OPTIONS'])
def fda_generate():
    """
    Footage Director Assistant (FDA) - LLM-assisted shot_plan generation.
    
    Standalone endpoint pro testování FDA mimo hlavní pipeline.
    
    Vstup:
    - tts_ready_package: objekt s narration_blocks[] nebo tts_segments[]
    - NEBO celý script_state
    - Optional: provider, model, temperature (pro LLM config)
    
    Výstup:
    - shot_plan: JSON objekt s scénami a shot strategií
    
    LLM: gpt-4o-mini (default), temp 0.2
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response
    
    try:
        from footage_director import run_fda_standalone
        
        data = request.get_json() or {}
        
        # Tolerance: přijmi různé vstupní formáty
        if 'tts_ready_package' in data:
            tts_package = data['tts_ready_package']
        elif 'script_state' in data:
            # Pokud posláno celé script_state, extrahuj tts_ready_package
            script_state = data['script_state']
            tts_package = script_state.get('tts_ready_package')
            if not tts_package:
                return jsonify({
                    'success': False,
                    'error': 'script_state neobsahuje tts_ready_package'
                }), 400
        elif 'narration_blocks' in data:
            # Přímo narration_blocks (pro jednoduchost)
            tts_package = {'narration_blocks': data['narration_blocks']}
        else:
            return jsonify({
                'success': False,
                'error': 'Chybí tts_ready_package nebo narration_blocks',
                'hint': 'Pošlete { "tts_ready_package": { "narration_blocks": [...] } }'
            }), 400
        
        # LLM config (optional)
        config = {
            'provider': data.get('provider', 'openrouter'),
            'model': data.get('model', 'openai/gpt-4o-mini'),
            'temperature': data.get('temperature', 0.2),
        }
        
        # API keys
        provider_api_keys = {
            'openai': os.getenv('OPENAI_API_KEY') or '',
            'openrouter': os.getenv('OPENROUTER_API_KEY') or '',
        }
        
        # Zavolej LLM-assisted FDA
        shot_plan = run_fda_standalone(tts_package, provider_api_keys, config)
        
        return jsonify({
            'success': True,
            'shot_plan': shot_plan,
            'summary': {
                'total_scenes': shot_plan.get('total_scenes', len(shot_plan.get('scenes', []) or [])),
                'total_duration_sec': shot_plan.get('total_duration_sec', 0),
                'version': shot_plan.get('version', 'unknown'),
            }
        })
        
    except ValueError as e:
        error_msg = str(e)
        if 'FDA_INPUT_MISSING' in error_msg:
            return jsonify({'success': False, 'error': error_msg}), 400
        if 'FDA_VALIDATION_FAILED' in error_msg:
            return jsonify({'success': False, 'error': error_msg}), 422
        return jsonify({'success': False, 'error': error_msg}), 400
    except RuntimeError as e:
        error_msg = str(e)
        if 'API key' in error_msg or 'LLM' in error_msg:
            return jsonify({'success': False, 'error': error_msg}), 500
        return jsonify({'success': False, 'error': error_msg}), 500
    except Exception as e:
        import traceback
        print(f"❌ FDA endpoint error: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/settings/llm_defaults', methods=['GET', 'POST', 'OPTIONS'])
def llm_defaults():
    """
    Global defaults for LLM steps 1-3.
    Stored in podcasts/config/llm_defaults.json
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'GET,POST')
        return response

    try:
        if request.method == 'GET':
            defaults = settings_store.read_llm_defaults()
            return jsonify({'success': True, 'data': defaults})

        data = request.get_json() or {}
        # Expected shape: { research: {...}, narrative: {...}, validation: {...}, tts_format: {...} }
        if not isinstance(data, dict):
            return jsonify({'success': False, 'error': 'Neplatný JSON'}), 400
        for key in ('research', 'narrative', 'validation', 'tts_format'):
            if key not in data or not isinstance(data.get(key), dict):
                return jsonify({'success': False, 'error': f'Chybí config pro krok: {key}'}), 400
        settings_store.write_llm_defaults(data)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/settings/global_preferences', methods=['GET', 'POST', 'OPTIONS'])
def global_preferences():
    """
    Global user preferences (music gain, etc.).
    Stored in podcasts/config/global_preferences.json
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'GET,POST')
        return response

    try:
        if request.method == 'GET':
            prefs = settings_store.read_global_preferences()
            return jsonify({'success': True, 'data': prefs})

        data = request.get_json() or {}
        if not isinstance(data, dict):
            return jsonify({'success': False, 'error': 'Neplatný JSON'}), 400
        
        # Validate music_bg_gain_db if present
        if 'music_bg_gain_db' in data:
            try:
                gain = float(data['music_bg_gain_db'])
                if gain < -60.0 or gain > 0.0:
                    return jsonify({'success': False, 'error': 'music_bg_gain_db musí být mezi -60 a 0 dB'}), 400
            except (ValueError, TypeError):
                return jsonify({'success': False, 'error': 'music_bg_gain_db musí být číslo'}), 400
        
        settings_store.write_global_preferences(data)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/settings/openai_status', methods=['GET'])
def openai_status():
    """
    Server-side OpenAI key status. Never returns the key.
    """
    try:
        return jsonify({'success': True, 'configured': settings_store.openai_key_configured()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/settings/openai_key', methods=['POST', 'OPTIONS'])
def save_openai_key():
    """
    Save OpenAI key server-side (backend/.env). Never returns it back.
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response

    try:
        data = request.get_json() or {}
        api_key = (data.get('openai_api_key') or '').strip()
        settings_store.save_openai_key(api_key)
        return jsonify({'success': True, 'configured': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/settings/elevenlabs_status', methods=['GET'])
def elevenlabs_status():
    """
    Server-side ElevenLabs key status. Never returns the key.
    """
    try:
        return jsonify({'success': True, 'configured': settings_store.elevenlabs_key_configured()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/settings/elevenlabs_key', methods=['POST', 'OPTIONS'])
def save_elevenlabs_key():
    """
    Save ElevenLabs key server-side (backend/.env). Never returns it back.
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response

    try:
        data = request.get_json() or {}
        api_key = (data.get('elevenlabs_api_key') or '').strip()
        settings_store.save_elevenlabs_key(api_key)
        return jsonify({'success': True, 'configured': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/settings/youtube_status', methods=['GET'])
def youtube_status():
    """
    Server-side YouTube key status. Never returns the key.
    """
    try:
        return jsonify({'success': True, 'configured': settings_store.youtube_key_configured()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/settings/youtube_key', methods=['POST', 'OPTIONS'])
def save_youtube_key():
    """
    Save YouTube key server-side (backend/.env as YOUTUBE_API_KEY). Never returns it back.
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response

    try:
        data = request.get_json() or {}
        api_key = (data.get('youtube_api_key') or '').strip()
        settings_store.save_youtube_key(api_key)
        return jsonify({'success': True, 'configured': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/settings/openrouter_status', methods=['GET'])
def openrouter_status():
    """
    Server-side OpenRouter key status. Never returns the key.
    """
    try:
        return jsonify({'success': True, 'configured': settings_store.openrouter_key_configured()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/settings/openrouter_key', methods=['POST', 'OPTIONS'])
def save_openrouter_key():
    """
    Save OpenRouter key server-side (backend/.env as OPENROUTER_API_KEY). Never returns it back.
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response

    try:
        data = request.get_json() or {}
        api_key = (data.get('openrouter_api_key') or '').strip()
        settings_store.save_openrouter_key(api_key)
        return jsonify({'success': True, 'configured': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/tts/generate', methods=['POST', 'OPTIONS'])
def generate_tts():
    """
    MVP Google Cloud Text-to-Speech endpoint
    Přijme tts_ready_package (nebo ScriptPackage), vygeneruje MP3 per-block
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response
    
    try:
        # Import pro REST API
        import time
        import base64
        import json as json_lib
        
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'Žádná data nebyla poslána'
            }), 400

        # Optional: episode_id for per-episode persistence
        episode_id = (data.get('episode_id') or '').strip()
        
        # Tolerantní přístup: přijmi buď tts_ready_package nebo celé ScriptPackage
        tts_package = None
        if 'tts_ready_package' in data:
            tts_package = data['tts_ready_package']
        elif 'script_package' in data and isinstance(data['script_package'], dict):
            # ScriptPackage může obsahovat tts_ready_package
            script_pkg = data['script_package']
            if 'tts_ready_package' in script_pkg:
                tts_package = script_pkg['tts_ready_package']
            elif 'narration_blocks' in script_pkg:
                # Použij přímo narration_blocks z script_package
                tts_package = script_pkg
        elif 'narration_blocks' in data:
            # Přímý input narration_blocks[]
            tts_package = data
        
        if not tts_package or 'narration_blocks' not in tts_package:
            return jsonify({
                'success': False,
                'error': 'Chybí narration_blocks v tts_ready_package',
                'hint': 'Pošlete { "tts_ready_package": { "narration_blocks": [...] } }'
            }), 400
        
        narration_blocks = tts_package.get('narration_blocks', [])
        
        if not narration_blocks or len(narration_blocks) == 0:
            return jsonify({
                'success': False,
                'error': 'narration_blocks je prázdné',
                'total_blocks': 0
            }), 400
        
        print(f"🎤 TTS GENERATE: Začínám generování {len(narration_blocks)} bloků")
        
        # Načti ENV konfiguraci
        voice_name = os.getenv('GCP_TTS_VOICE_NAME', 'en-US-Neural2-D')
        language_code = os.getenv('GCP_TTS_LANGUAGE_CODE', 'en-US')
        speaking_rate = float(os.getenv('GCP_TTS_SPEAKING_RATE', '1.0'))
        pitch = float(os.getenv('GCP_TTS_PITCH', '0.0'))
        
        # Validace GOOGLE_APPLICATION_CREDENTIALS
        credentials_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        if not credentials_path:
            return jsonify({
                'success': False,
                'error': 'Chybí GOOGLE_APPLICATION_CREDENTIALS v .env',
                'hint': 'Nastavte cestu k service account JSON souboru'
            }), 500
        
        if not os.path.exists(credentials_path):
            return jsonify({
                'success': False,
                'error': f'Service account soubor neexistuje: {credentials_path}',
                'hint': 'Zkontrolujte cestu v GOOGLE_APPLICATION_CREDENTIALS'
            }), 500
        
        # SSML enhancement settings (pro přirozenější výstup)
        use_ssml = os.getenv('GCP_TTS_USE_SSML', 'true').lower() == 'true'
        # Audio effects profile pro lepší kvalitu (headphone-class-device, large-home-entertainment-class-device, etc.)
        effects_profile = os.getenv('GCP_TTS_EFFECTS_PROFILE', 'headphone-class-device')
        
        print(f"🔧 TTS CONFIG: voice={voice_name}, language={language_code}, rate={speaking_rate}, pitch={pitch}, ssml={use_ssml}, effects={effects_profile}")
        
        # Google Cloud TTS REST API endpoint
        tts_api_url = "https://texttospeech.googleapis.com/v1/text:synthesize"
        
        # ============================================================
        # SSML Pre-processing pro přirozenější TTS výstup
        # ============================================================
        def normalize_text_for_tts(text: str, lang_code: str) -> str:
            """
            Normalizuje text pro lepší TTS výslovnost:
            - Expanduje běžné zkratky
            - Formátuje čísla pro správnou výslovnost
            - Odstraňuje problematické znaky
            """
            import re
            
            if not text:
                return text
            
            result = text.strip()
            
            # Odstranění více mezer za sebou
            result = re.sub(r'\s+', ' ', result)
            
            # Expandování běžných zkratek (case-insensitive)
            abbreviations_en = {
                r'\bDr\.': 'Doctor',
                r'\bMr\.': 'Mister',
                r'\bMrs\.': 'Missus',
                r'\bMs\.': 'Miss',
                r'\bSt\.': 'Saint',
                r'\bvs\.': 'versus',
                r'\betc\.': 'etcetera',
                r'\be\.g\.': 'for example',
                r'\bi\.e\.': 'that is',
                r'\bU\.S\.A\.': 'United States of America',
                r'\bU\.S\.': 'United States',
                r'\bU\.K\.': 'United Kingdom',
                r'\bWWII': 'World War Two',
                r'\bWWI': 'World War One',
                r'\bSSR': 'Soviet Socialist Republic',
                r'\bUSSR': 'U S S R',
                r'\bNATO': 'NATO',  # already readable
                r'\bCEO': 'C E O',
                r'\bFBI': 'F B I',
                r'\bCIA': 'C I A',
                r'\bNASA': 'NASA',  # already readable
            }
            
            if lang_code.startswith('en'):
                for pattern, replacement in abbreviations_en.items():
                    result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
            
            # Formátování roků pro lepší výslovnost (1945 → nineteen forty-five)
            # Pouze 4-místná čísla začínající 1 nebo 2 (pravděpodobně roky)
            def year_to_words(match):
                year = int(match.group(0))
                if 1000 <= year <= 2099:
                    if year < 2000:
                        century = year // 100
                        decade = year % 100
                        century_words = {10: 'ten', 11: 'eleven', 12: 'twelve', 13: 'thirteen',
                                         14: 'fourteen', 15: 'fifteen', 16: 'sixteen', 17: 'seventeen',
                                         18: 'eighteen', 19: 'nineteen'}
                        decade_words = {0: 'hundred', 1: 'oh one', 2: 'oh two', 3: 'oh three',
                                        4: 'oh four', 5: 'oh five', 6: 'oh six', 7: 'oh seven',
                                        8: 'oh eight', 9: 'oh nine', 10: 'ten', 11: 'eleven',
                                        12: 'twelve', 13: 'thirteen', 14: 'fourteen', 15: 'fifteen',
                                        16: 'sixteen', 17: 'seventeen', 18: 'eighteen', 19: 'nineteen',
                                        20: 'twenty', 21: 'twenty-one', 22: 'twenty-two', 23: 'twenty-three',
                                        24: 'twenty-four', 25: 'twenty-five', 26: 'twenty-six', 27: 'twenty-seven',
                                        28: 'twenty-eight', 29: 'twenty-nine', 30: 'thirty', 31: 'thirty-one',
                                        32: 'thirty-two', 33: 'thirty-three', 34: 'thirty-four', 35: 'thirty-five',
                                        36: 'thirty-six', 37: 'thirty-seven', 38: 'thirty-eight', 39: 'thirty-nine',
                                        40: 'forty', 41: 'forty-one', 42: 'forty-two', 43: 'forty-three',
                                        44: 'forty-four', 45: 'forty-five', 46: 'forty-six', 47: 'forty-seven',
                                        48: 'forty-eight', 49: 'forty-nine', 50: 'fifty', 51: 'fifty-one',
                                        52: 'fifty-two', 53: 'fifty-three', 54: 'fifty-four', 55: 'fifty-five',
                                        56: 'fifty-six', 57: 'fifty-seven', 58: 'fifty-eight', 59: 'fifty-nine',
                                        60: 'sixty', 61: 'sixty-one', 62: 'sixty-two', 63: 'sixty-three',
                                        64: 'sixty-four', 65: 'sixty-five', 66: 'sixty-six', 67: 'sixty-seven',
                                        68: 'sixty-eight', 69: 'sixty-nine', 70: 'seventy', 71: 'seventy-one',
                                        72: 'seventy-two', 73: 'seventy-three', 74: 'seventy-four', 75: 'seventy-five',
                                        76: 'seventy-six', 77: 'seventy-seven', 78: 'seventy-eight', 79: 'seventy-nine',
                                        80: 'eighty', 81: 'eighty-one', 82: 'eighty-two', 83: 'eighty-three',
                                        84: 'eighty-four', 85: 'eighty-five', 86: 'eighty-six', 87: 'eighty-seven',
                                        88: 'eighty-eight', 89: 'eighty-nine', 90: 'ninety', 91: 'ninety-one',
                                        92: 'ninety-two', 93: 'ninety-three', 94: 'ninety-four', 95: 'ninety-five',
                                        96: 'ninety-six', 97: 'ninety-seven', 98: 'ninety-eight', 99: 'ninety-nine'}
                        if century in century_words and decade in decade_words:
                            return f"{century_words[century]} {decade_words[decade]}"
                    elif 2000 <= year <= 2009:
                        ones = ['', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine']
                        return f"two thousand {ones[year - 2000]}".strip()
                    elif 2010 <= year <= 2099:
                        decade = year - 2000
                        decade_words = {10: 'ten', 11: 'eleven', 12: 'twelve', 13: 'thirteen',
                                        14: 'fourteen', 15: 'fifteen', 16: 'sixteen', 17: 'seventeen',
                                        18: 'eighteen', 19: 'nineteen', 20: 'twenty', 21: 'twenty-one',
                                        22: 'twenty-two', 23: 'twenty-three', 24: 'twenty-four', 25: 'twenty-five'}
                        if decade in decade_words:
                            return f"twenty {decade_words[decade]}"
                return match.group(0)  # fallback - keep original
            
            # Pouze roky v kontextu (ne všechna 4-místná čísla)
            result = re.sub(r'\b(1[0-9]{3}|20[0-2][0-9])\b', year_to_words, result)
            
            # Odstranění markdown formátování
            result = re.sub(r'\*\*([^*]+)\*\*', r'\1', result)  # **bold**
            result = re.sub(r'\*([^*]+)\*', r'\1', result)      # *italic*
            result = re.sub(r'__([^_]+)__', r'\1', result)      # __bold__
            result = re.sub(r'_([^_]+)_', r'\1', result)        # _italic_
            
            # Nahrazení problematických znaků
            result = result.replace('—', ', ')  # em-dash → čárka s pauzou
            result = result.replace('–', ', ')  # en-dash → čárka s pauzou
            result = result.replace('…', '.')    # ellipsis → tečka
            result = result.replace('"', '')     # smart quotes
            result = result.replace('"', '')
            result = result.replace(''', "'")
            result = result.replace(''', "'")
            
            return result.strip()
        
        def text_to_ssml(text: str, lang_code: str) -> str:
            """
            Konvertuje plain text na SSML pro Google TTS.
            Přidává přirozené pauzy a prosodické značky.
            """
            import re
            
            if not text:
                return '<speak></speak>'
            
            # Nejdřív normalizuj text
            normalized = normalize_text_for_tts(text, lang_code)
            
            # Escape XML special characters
            normalized = normalized.replace('&', '&amp;')
            normalized = normalized.replace('<', '&lt;')
            normalized = normalized.replace('>', '&gt;')
            
            # Přidej pauzy po větách (. ! ?)
            # Krátká pauza po běžné větě
            normalized = re.sub(r'\.(\s+)', r'.<break time="400ms"/>\1', normalized)
            # Delší pauza po otázce/vykřičníku
            normalized = re.sub(r'\?(\s+)', r'?<break time="500ms"/>\1', normalized)
            normalized = re.sub(r'!(\s+)', r'!<break time="450ms"/>\1', normalized)
            
            # Kratší pauza po čárce
            normalized = re.sub(r',(\s+)', r',<break time="200ms"/>\1', normalized)
            
            # Pauza po středníku a dvojtečce
            normalized = re.sub(r';(\s+)', r';<break time="350ms"/>\1', normalized)
            normalized = re.sub(r':(\s+)', r':<break time="300ms"/>\1', normalized)
            
            # Obal do <speak> tagu
            ssml = f'<speak>{normalized}</speak>'
            
            return ssml
        
        # Helper funkce pro získání access token (s explicitním refresh)
        def get_access_token_with_refresh():
            """
            Získej a refreshni access token z service account JSON.
            Returns: (token_string, error_message_or_none)
            """
            try:
                from google.oauth2 import service_account
                import google.auth.transport.requests
                
                # Load credentials
                credentials = service_account.Credentials.from_service_account_file(
                    credentials_path,
                    scopes=['https://www.googleapis.com/auth/cloud-platform']
                )
                
                # CRITICAL: Explicitně refreshni token před použitím
                auth_req = google.auth.transport.requests.Request()
                credentials.refresh(auth_req)
                
                # Teď token existuje a není None
                if not credentials.token:
                    return None, "Token refresh proběhl, ale token je stále None"
                
                print(f"🔑 Access token úspěšně vygenerován (expires: {credentials.expiry})")
                return credentials.token, None
                
            except FileNotFoundError:
                return None, f"TTS_AUTH_REFRESH_FAILED: Service account soubor nenalezen: {credentials_path}"
            except ValueError as e:
                return None, f"TTS_AUTH_REFRESH_FAILED: Neplatný JSON v service account: {str(e)}"
            except Exception as e:
                error_str = str(e)
                if "Permission denied" in error_str or "forbidden" in error_str.lower():
                    return None, f"TTS_AUTH_REFRESH_FAILED: Permissions chyba - zkontrolujte service account role: {error_str}"
                else:
                    return None, f"TTS_AUTH_REFRESH_FAILED: {error_str}"
        
        # Vyber output dir:
        # - prefer per-episode folder: projects/<episode_id>/voiceover/
        # - fallback: uploads/ (legacy)
        tts_output_dir = UPLOAD_FOLDER
        if episode_id:
            try:
                if project_store.exists(episode_id):
                    ep_dir = project_store.episode_dir(episode_id)
                    tts_output_dir = os.path.join(ep_dir, "voiceover")
                else:
                    # pokud epizoda neexistuje, stále vytvoř per-episode složku (neztratíme data při refreshi)
                    ep_dir = project_store.episode_dir(episode_id)
                    os.makedirs(ep_dir, exist_ok=True)
                    tts_output_dir = os.path.join(ep_dir, "voiceover")
            except Exception:
                tts_output_dir = UPLOAD_FOLDER

        os.makedirs(tts_output_dir, exist_ok=True)
        
        # Získej access token pro API (1× pro celý běh - TOKEN CACHE)
        print(f"🔑 Získávám access token z service account...")
        access_token, token_error = get_access_token_with_refresh()
        
        if token_error:
            print(f"❌ {token_error}")
            return jsonify({
                'success': False,
                'error': token_error,
                'hint': 'Zkontrolujte GOOGLE_APPLICATION_CREDENTIALS, service account permissions, a že Cloud Text-to-Speech API je zapnutá'
            }), 500
        
        print(f"✅ Access token získán - použije se pro všechny bloky ({len(narration_blocks)} bloků)")
        
        # Helper pro refresh tokenu při 401 (během běhu)
        def refresh_token_if_needed():
            """Jednorázový refresh při 401 během běhu"""
            nonlocal access_token
            print(f"🔄 Token expiroval, refreshuji...")
            new_token, error = get_access_token_with_refresh()
            if error:
                raise Exception(f"Token refresh selhal: {error}")
            access_token = new_token
            print(f"✅ Token refreshnut")
            return access_token
        
        # Smaž staré Narrator_*.mp3 pouze v cílové složce (per-episode nebo legacy uploads)
        print(f"🧹 Mažu staré Narrator_*.mp3 soubory z {tts_output_dir}")
        try:
            for filename in os.listdir(tts_output_dir):
                if filename.startswith('Narrator_') and filename.endswith('.mp3'):
                    old_path = os.path.join(tts_output_dir, filename)
                    try:
                        os.remove(old_path)
                        print(f"  ✅ Smazán: {filename}")
                    except Exception as e:
                        print(f"  ⚠️ Nepodařilo se smazat {filename}: {e}")
        except Exception as e:
            print(f"  ⚠️ Nepodařilo se projít složku {tts_output_dir}: {e}")
        
        # Headers pro REST API
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        # Generování per-block s retry
        generated_blocks = []
        failed_blocks = []
        
        for i, block in enumerate(narration_blocks, start=1):
            block_id = block.get('block_id', f'unknown_{i}')
            text_tts = block.get('text_tts', '')
            
            # Validace bloku
            if not text_tts or text_tts.strip() == '':
                print(f"⚠️ Block {i} ({block_id}): text_tts je prázdný, přeskakuji")
                failed_blocks.append({
                    'index': i,
                    'block_id': block_id,
                    'error': 'text_tts je prázdný'
                })
                continue
            
            # Filename s fixed-width číslováním
            filename = f'Narrator_{i:04d}.mp3'
            file_path = os.path.join(tts_output_dir, filename)
            
            print(f"🎤 Block {i}/{len(narration_blocks)} ({block_id}): Generuji '{text_tts[:50]}...'")
            
            # Retry logika (max 3 pokusy)
            max_retries = 3
            retry_delay = 1.0  # seconds
            success = False
            last_error = None
            token_refreshed = False  # Track jestli už byl token refreshnut pro tento block
            
            for attempt in range(1, max_retries + 1):
                try:
                    # Google TTS REST API call
                    # Použij SSML pro přirozenější výstup (pokud je povoleno)
                    if use_ssml:
                        ssml_text = text_to_ssml(text_tts, language_code)
                        input_payload = {"ssml": ssml_text}
                    else:
                        # Fallback na plain text (s normalizací)
                        normalized_text = normalize_text_for_tts(text_tts, language_code)
                        input_payload = {"text": normalized_text}
                    
                    # Audio config s effects profile pro lepší kvalitu
                    audio_config = {
                        "audioEncoding": "MP3",
                        "speakingRate": speaking_rate,
                        "pitch": pitch
                    }
                    
                    # Přidej effects profile pokud je nastaven (optimalizuje audio)
                    if effects_profile:
                        audio_config["effectsProfileId"] = [effects_profile]
                    
                    request_body = {
                        "input": input_payload,
                        "voice": {
                            "languageCode": language_code,
                            "name": voice_name
                        },
                        "audioConfig": audio_config
                    }
                    
                    response = requests.post(
                        tts_api_url,
                        headers=headers,
                        json=request_body,
                        timeout=30
                    )
                    
                    # Handle HTTP errors s jasnými messages
                    if response.status_code == 401:
                        # Unauthorized - token expiroval nebo je neplatný
                        if not token_refreshed:
                            print(f"  ⚠️ Block {i} attempt {attempt}: 401 Unauthorized, refreshuji token...")
                            try:
                                new_token = refresh_token_if_needed()
                                headers['Authorization'] = f'Bearer {new_token}'
                                token_refreshed = True
                                # Retry s novým tokenem (nezvyšuj attempt counter)
                                continue
                            except Exception as refresh_error:
                                raise Exception(f"401 Unauthorized + token refresh selhal: {refresh_error}")
                        else:
                            raise Exception(f"401 Unauthorized i po token refresh - zkontrolujte service account permissions")
                    
                    elif response.status_code == 403:
                        # Forbidden - permissions/API disabled/billing
                        response_body = response.text[:500]
                        raise Exception(f"403 Forbidden: API pravděpodobně vypnutá, chybí billing nebo service account nemá správnou roli. Details: {response_body}")
                    
                    elif response.status_code == 400:
                        # Bad request - payload problém (ne retry)
                        response_body = response.text[:500]
                        last_error = f"400 Bad Request (payload/voice chyba): {response_body}"
                        print(f"  ❌ Block {i}: {last_error}")
                        # Ne retry - je to payload problém
                        break
                    
                    elif response.status_code == 429:
                        raise Exception("Rate limit (429)")
                    
                    elif response.status_code >= 500:
                        raise Exception(f"Server error ({response.status_code})")
                    
                    elif response.status_code != 200:
                        raise Exception(f"API error ({response.status_code}): {response.text[:200]}")
                    
                    # Parse response
                    response_data = response.json()
                    audio_content_base64 = response_data.get('audioContent')
                    
                    if not audio_content_base64:
                        raise Exception("Response missing audioContent")
                    
                    # Decode base64 to binary
                    audio_bytes = base64.b64decode(audio_content_base64)
                    
                    # Ulož MP3 binárně
                    with open(file_path, 'wb') as out:
                        out.write(audio_bytes)
                    
                    print(f"  ✅ Block {i} uložen: {filename} ({len(audio_bytes)} bytes)")
                    generated_blocks.append({
                        'index': i,
                        'block_id': block_id,
                        'filename': filename,
                        'size_bytes': len(audio_bytes)
                    })
                    success = True
                    break  # Success, exit retry loop
                    
                except requests.exceptions.Timeout:
                    last_error = "Request timeout"
                    print(f"  ⚠️ Block {i} attempt {attempt}/{max_retries}: Timeout, čekám {retry_delay}s")
                    if attempt < max_retries:
                        time.sleep(retry_delay)
                        retry_delay *= 2
                    
                except Exception as e:
                    error_str = str(e)
                    last_error = error_str
                    
                    # 400 Bad Request - ne retry
                    if "400 Bad Request" in error_str:
                        break  # Už je v last_error, ne retry
                    
                    # 403 Forbidden - ne retry (permissions/API)
                    if "403 Forbidden" in error_str:
                        print(f"  ❌ Block {i}: {error_str}")
                        break  # Ne retry - je to permissions problém
                    
                    # Rate limit - retry
                    if "429" in error_str or "Rate limit" in error_str:
                        print(f"  ⚠️ Block {i} attempt {attempt}/{max_retries}: Rate limit, čekám {retry_delay}s")
                    # Server error - retry
                    elif "5" in error_str[:3]:
                        print(f"  ⚠️ Block {i} attempt {attempt}/{max_retries}: Server error, čekám {retry_delay}s")
                    # Ostatní chyby
                    else:
                        print(f"  ⚠️ Block {i} attempt {attempt}/{max_retries}: {error_str[:200]}")
                    
                    if attempt < max_retries:
                        time.sleep(retry_delay)
                        retry_delay *= 2
            
            if not success:
                print(f"  ❌ Block {i} ({block_id}): FAILED po {max_retries} pokusech: {last_error}")
                failed_blocks.append({
                    'index': i,
                    'block_id': block_id,
                    'error': last_error
                })
        
        # Souhrn
        total_blocks = len(narration_blocks)
        generated_count = len(generated_blocks)
        failed_count = len(failed_blocks)
        
        print(f"📊 TTS GENERATE: Hotovo! {generated_count}/{total_blocks} úspěšných, {failed_count} failů")
        
        # Persist do script_state, pokud máme episode_id
        if episode_id:
            try:
                state = project_store.read_script_state(episode_id) if project_store.exists(episode_id) else {}
                if not isinstance(state, dict):
                    state = {}
                state["tts_generated_files"] = [b["filename"] for b in generated_blocks]
                state["tts_generated_dir"] = tts_output_dir
                state["tts_generated_count"] = len(generated_blocks)
                state["tts_generated_failed_count"] = len(failed_blocks)
                project_store.write_script_state(episode_id, state)
            except Exception as e:
                print(f"⚠️ TTS: Nepodařilo se uložit tts_generated_files do script_state: {e}")

        generated_files = [b['filename'] for b in generated_blocks]
        generated_files_info = []
        for fname in generated_files:
            if episode_id and tts_output_dir != UPLOAD_FOLDER:
                generated_files_info.append({
                    "filename": fname,
                    "url": f"/api/projects/{episode_id}/audio/{fname}"
                })
            else:
                generated_files_info.append({
                    "filename": fname,
                    "url": f"/api/download/{fname}"
                })

        return jsonify({
            'success': generated_count > 0,
            'total_blocks': total_blocks,
            'generated_blocks': generated_count,
            'failed_blocks_count': failed_count,
            'failed_blocks': failed_blocks,
            'episode_id': episode_id or None,
            'output_dir': tts_output_dir,
            'message': f'Vygenerováno {generated_count}/{total_blocks} audio bloků',
            'generated_files': generated_files,
            'generated_files_info': generated_files_info
        })
        
    except Exception as e:
        print(f"❌ TTS GENERATE: Kritická chyba: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'total_blocks': 0,
            'generated_blocks': 0
        }), 500


@app.route('/api/tts/test', methods=['POST', 'OPTIONS'])
def test_tts_quality():
    """
    Testovací endpoint pro TTS kvalitu.
    Vygeneruje krátký audio sample s aktuálním nastavením.
    
    Request body:
    {
        "text": "Test sentence to synthesize.",
        "use_ssml": true/false (optional, defaults to env setting),
        "voice_name": "en-US-Journey-D" (optional),
        "speaking_rate": 0.95 (optional),
        "pitch": -1.0 (optional)
    }
    
    Returns MP3 audio file directly.
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response
    
    try:
        import base64
        import re
        
        data = request.get_json() or {}
        text = data.get('text', 'This is a test of the text to speech system. In nineteen forty-five, the world changed forever.')
        
        # Načti konfigurace (s override možností)
        voice_name = data.get('voice_name', os.getenv('GCP_TTS_VOICE_NAME', 'en-US-Neural2-D'))
        language_code = data.get('language_code', os.getenv('GCP_TTS_LANGUAGE_CODE', 'en-US'))
        speaking_rate = float(data.get('speaking_rate', os.getenv('GCP_TTS_SPEAKING_RATE', '1.0')))
        pitch = float(data.get('pitch', os.getenv('GCP_TTS_PITCH', '0.0')))
        use_ssml = data.get('use_ssml', os.getenv('GCP_TTS_USE_SSML', 'true').lower() == 'true')
        effects_profile = data.get('effects_profile', os.getenv('GCP_TTS_EFFECTS_PROFILE', 'headphone-class-device'))
        
        # Validace credentials
        credentials_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        if not credentials_path or not os.path.exists(credentials_path):
            return jsonify({
                'success': False,
                'error': 'Google credentials not configured'
            }), 500
        
        # Get access token
        from google.oauth2 import service_account
        import google.auth.transport.requests
        
        credentials = service_account.Credentials.from_service_account_file(
            credentials_path,
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
        auth_req = google.auth.transport.requests.Request()
        credentials.refresh(auth_req)
        
        # Funkce pro SSML konverzi (zjednodušená verze)
        def simple_text_to_ssml(txt: str) -> str:
            # Escape XML
            txt = txt.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            # Pauzy
            txt = re.sub(r'\.(\s+)', r'.<break time="400ms"/>\1', txt)
            txt = re.sub(r',(\s+)', r',<break time="200ms"/>\1', txt)
            return f'<speak>{txt}</speak>'
        
        # Připrav input
        if use_ssml:
            input_payload = {"ssml": simple_text_to_ssml(text)}
        else:
            input_payload = {"text": text}
        
        # Audio config
        audio_config = {
            "audioEncoding": "MP3",
            "speakingRate": speaking_rate,
            "pitch": pitch
        }
        if effects_profile:
            audio_config["effectsProfileId"] = [effects_profile]
        
        # API call
        response = requests.post(
            "https://texttospeech.googleapis.com/v1/text:synthesize",
            headers={
                'Authorization': f'Bearer {credentials.token}',
                'Content-Type': 'application/json'
            },
            json={
                "input": input_payload,
                "voice": {
                    "languageCode": language_code,
                    "name": voice_name
                },
                "audioConfig": audio_config
            },
            timeout=30
        )
        
        if response.status_code != 200:
            return jsonify({
                'success': False,
                'error': f'TTS API error: {response.status_code}',
                'details': response.text[:500]
            }), response.status_code
        
        # Return audio
        audio_content = base64.b64decode(response.json()['audioContent'])
        
        from flask import Response
        return Response(
            audio_content,
            mimetype='audio/mpeg',
            headers={
                'Content-Disposition': 'attachment; filename=tts_test.mp3',
                'X-TTS-Voice': voice_name,
                'X-TTS-SSML': str(use_ssml),
                'X-TTS-Rate': str(speaking_rate),
                'X-TTS-Pitch': str(pitch),
                'X-TTS-Effects': effects_profile or 'none'
            }
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/tts/config', methods=['GET'])
def get_tts_config():
    """
    Vrátí aktuální TTS konfiguraci pro debugging a diagnostiku.
    """
    return jsonify({
        'success': True,
        'config': {
            'voice_name': os.getenv('GCP_TTS_VOICE_NAME', 'en-US-Neural2-D'),
            'language_code': os.getenv('GCP_TTS_LANGUAGE_CODE', 'en-US'),
            'speaking_rate': float(os.getenv('GCP_TTS_SPEAKING_RATE', '1.0')),
            'pitch': float(os.getenv('GCP_TTS_PITCH', '0.0')),
            'use_ssml': os.getenv('GCP_TTS_USE_SSML', 'true').lower() == 'true',
            'effects_profile': os.getenv('GCP_TTS_EFFECTS_PROFILE', 'headphone-class-device'),
            'credentials_configured': bool(os.getenv('GOOGLE_APPLICATION_CREDENTIALS'))
        },
        'recommended_voices': {
            'most_natural_male': 'en-US-Journey-D',
            'most_natural_female': 'en-US-Journey-F',
            'studio_male': 'en-US-Studio-O',
            'studio_female': 'en-US-Studio-Q',
            'neural_male': 'en-US-Neural2-D',
            'neural_female': 'en-US-Neural2-F'
        },
        'tips': [
            'Journey voices are the most natural sounding',
            'Speaking rate 0.92-0.95 sounds more natural for documentaries',
            'Negative pitch (-1 to -2) makes male voices deeper and more authoritative',
            'SSML adds natural pauses and improves rhythm',
            'headphone-class-device effects profile works best for YouTube'
        ]
    })


@app.route('/api/video/episode-pool/<episode_id>', methods=['GET', 'OPTIONS'])
def get_episode_pool(episode_id):
    """
    Vrátí CELÝ episode pool (všechny nalezené assets) místo per-beat view.
    Uživatel chce vidět VŠECHNO co AAR našlo, ne jen subset pro každý beat.
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'GET')
        return response
    
    try:
        from project_store import ProjectStore
        import json as json_lib
        
        store = ProjectStore(PROJECTS_FOLDER)
        episode_dir = store.episode_dir(episode_id)
        manifest_path = os.path.join(episode_dir, 'archive_manifest.json')
        
        if not os.path.exists(manifest_path):
            return jsonify({
                'success': False,
                'error': 'Archive manifest neexistuje - spusť nejdřív Preview Videa (AAR).',
            }), 404
        
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json_lib.load(f)
        
        # Extract episode pool data (transparency-first schema)
        episode_pool = manifest.get('episode_pool') or {}
        queries_used = episode_pool.get('queries_used') or []
        stats = episode_pool.get('stats') or {}

        # Prefer explicit lists stored in episode_pool (raw/unique/selected) to avoid "black box".
        selected_ranked = episode_pool.get("selected_ranked") if isinstance(episode_pool.get("selected_ranked"), dict) else {}
        unique_ranked = episode_pool.get("unique_ranked") if isinstance(episode_pool.get("unique_ranked"), dict) else {}
        raw_candidates = episode_pool.get("raw_candidates") if isinstance(episode_pool.get("raw_candidates"), dict) else {}

        sel_videos = (selected_ranked.get("videos") or []) if isinstance(selected_ranked, dict) else []
        sel_images = (selected_ranked.get("images") or []) if isinstance(selected_ranked, dict) else []

        uniq_videos = (unique_ranked.get("videos") or []) if isinstance(unique_ranked, dict) else []
        uniq_images = (unique_ranked.get("images") or []) if isinstance(unique_ranked, dict) else []

        raw_videos = (raw_candidates.get("videos") or []) if isinstance(raw_candidates, dict) else []
        raw_images = (raw_candidates.get("images") or []) if isinstance(raw_candidates, dict) else []

        # Backward compat: if selected lists are missing, fall back to collecting from scenes.assets
        if not sel_videos and not sel_images:
            all_assets_map = {}  # archive_item_id -> asset data
            for scene in (manifest.get('scenes') or []):
                if not isinstance(scene, dict):
                    continue
                scene_assets = scene.get('assets') or []
                for asset in scene_assets:
                    if isinstance(asset, dict):
                        aid = str(asset.get('archive_item_id') or '').strip()
                        if aid and aid not in all_assets_map:
                            all_assets_map[aid] = asset
            all_assets = list(all_assets_map.values())
            sel_videos = [a for a in all_assets if a.get('media_type') == 'video']
            sel_images = [a for a in all_assets if a.get('media_type') == 'image']
        videos = sel_videos
        images = sel_images
        
        # Add thumbnail URLs
        def _split_source(aid: str) -> tuple:
            s = str(aid or "").strip()
            if ":" in s:
                p, r = s.split(":", 1)
                p = p.strip().lower()
                if p in ("archive", "archiveorg", "archive_org", "archive.org"):
                    return "archive_org", r
                if p in ("wikimedia", "commons", "wikimedia_commons"):
                    return "wikimedia", r
                if p in ("europeana",):
                    return "europeana", r
                return p or "other", r
            return "archive_org", s
        
        # Ensure thumbnail/source fields exist for selected assets
        for asset in list(videos) + list(images):
            aid = asset.get('archive_item_id', '')
            src, raw = _split_source(aid)
            if src == 'archive_org':
                if not asset.get('thumbnail_url'):
                    asset['thumbnail_url'] = f"https://archive.org/services/img/{raw}"
            asset['source'] = src
        
        return jsonify({
            'success': True,
            'episode_id': episode_id,
            'queries_used': queries_used,
            'stats': stats,
            'pool': {
                # Selected pool (used for compilation/distribution)
                'videos': videos,
                'images': images,
                'total_videos': len(videos),
                'total_images': len(images),
                'total_assets': len(videos) + len(images),
                # Transparency payloads (show EVERYTHING)
                'unique_ranked': {
                    'videos': uniq_videos,
                    'images': uniq_images,
                    'total_videos': len(uniq_videos),
                    'total_images': len(uniq_images),
                },
                'raw_candidates': {
                    'videos': raw_videos,
                    'images': raw_images,
                    'total_videos': len(raw_videos),
                    'total_images': len(raw_images),
                },
            },
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/video/archive-stats/<episode_id>', methods=['GET', 'OPTIONS'])
def get_archive_stats(episode_id):
    """
    Vrátí statistiky z archive_manifest.json pro daný episode.
    
    Output:
    - success: bool
    - stats: {
        total_candidates: int,
        video_candidates: int,
        image_candidates: int,
        scenes_with_candidates: int,
        scenes_without_candidates: int,
        total_scenes: int,
        manifest_exists: bool,
        manifest_path: str
      }
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'GET')
        return response
    
    try:
        from project_store import ProjectStore
        import json as json_lib
        
        store = ProjectStore(PROJECTS_FOLDER)
        episode_dir = store.episode_dir(episode_id)
        manifest_path = os.path.join(episode_dir, 'archive_manifest.json')
        
        if not os.path.exists(manifest_path):
            return jsonify({
                'success': False,
                'error': 'Archive manifest neexistuje - spusťte nejdřív AAR (Preview Videa)',
                'stats': {
                    'manifest_exists': False,
                    'manifest_path': manifest_path
                }
            }), 404
        
        # Parse manifest
        with open(manifest_path, 'r') as f:
            manifest = json_lib.load(f)
        
        # Check if we have episode_pool data (from step-by-step workflow)
        episode_pool = manifest.get('episode_pool')
        if episode_pool and isinstance(episode_pool, dict):
            # Use episode_pool stats if available (step-by-step workflow)
            selected_ranked = episode_pool.get('selected_ranked') or {}
            selected_videos = selected_ranked.get('videos') or []
            selected_images = selected_ranked.get('images') or []
            
            video_candidates = len(selected_videos)
            image_candidates = len(selected_images)
            total_candidates = video_candidates + image_candidates
            
            # Count by source
            by_source = {"archive_org": 0, "wikimedia": 0, "europeana": 0, "other": 0}
            
            # #region agent log
            try:
                import time as _time
                sample_sources = []
                for idx, v in enumerate(selected_videos[:3]):
                    sample_sources.append({
                        "type": "video",
                        "idx": idx,
                        "source_field": str(v.get("source") or ""),
                        "archive_item_id": str(v.get("archive_item_id") or "")[:80],
                    })
                for idx, i in enumerate(selected_images[:3]):
                    sample_sources.append({
                        "type": "image",
                        "idx": idx,
                        "source_field": str(i.get("source") or ""),
                        "archive_item_id": str(i.get("archive_item_id") or "")[:80],
                    })
                with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
                    _f.write(json.dumps({
                        "sessionId": "debug-session", "runId": "stats-parse", "hypothesisId": "STATS",
                        "location": "backend/app.py:get_archive_stats:episode_pool_mode",
                        "message": "Parsing episode_pool sources",
                        "data": {
                            "video_count": len(selected_videos),
                            "image_count": len(selected_images),
                            "sample_candidates": sample_sources,
                        },
                        "timestamp": int(_time.time() * 1000),
                    }) + "\n")
            except Exception:
                pass
            # #endregion
            
            def _infer_source_from_pool(candidate: dict) -> str:
                try:
                    src = str(candidate.get("source") or "").strip().lower()
                    if "archive" in src:
                        return "archive_org"
                    elif "wikimedia" in src or "commons" in src:
                        return "wikimedia"
                    elif "europeana" in src:
                        return "europeana"
                    
                    aid = str(candidate.get("archive_item_id") or "").strip()
                    if ":" in aid:
                        prefix = aid.split(":", 1)[0].strip().lower()
                        if prefix in ("archive", "archiveorg", "archive_org", "archive.org"):
                            return "archive_org"
                        if prefix in ("wikimedia", "commons", "wikimedia_commons"):
                            return "wikimedia"
                        if prefix in ("europeana",):
                            return "europeana"
                        return prefix or "other"
                    return "archive_org"
                except Exception:
                    return "other"
            
            for v in selected_videos:
                src = _infer_source_from_pool(v)
                by_source[src] = by_source.get(src, 0) + 1
            for i in selected_images:
                src = _infer_source_from_pool(i)
                by_source[src] = by_source.get(src, 0) + 1
            
            # #region agent log
            try:
                import time as _time
                with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
                    _f.write(json.dumps({
                        "sessionId": "debug-session", "runId": "stats-parse", "hypothesisId": "STATS",
                        "location": "backend/app.py:get_archive_stats:by_source_result",
                        "message": "Source counting finished",
                        "data": {"by_source": by_source},
                        "timestamp": int(_time.time() * 1000),
                    }) + "\n")
            except Exception:
                pass
            # #endregion
            
            # For episode_pool mode, we don't have per-scene data
            # Check if scenes exist in manifest
            scenes = manifest.get('scenes', [])
            total_scenes = len(scenes) if scenes else 0
            scenes_with_candidates = total_scenes if total_candidates > 0 else 0
            scenes_without_candidates = 0 if total_candidates > 0 else total_scenes
            
            return jsonify({
                'success': True,
                'stats': {
                    'total_candidates': total_candidates,
                    'video_candidates': video_candidates,
                    'image_candidates': image_candidates,
                    'scenes_with_candidates': scenes_with_candidates,
                    'scenes_without_candidates': scenes_without_candidates,
                    'total_scenes': total_scenes,
                    'manifest_exists': True,
                    'manifest_path': manifest_path,
                    'query_probe': None,
                    'by_source': by_source,
                    'mode': 'episode_pool'  # Indicator for UI
                }
            })
        
        # Fallback: Analyze candidates from scenes (old workflow)
        # scenes[].visual_beats[].asset_candidates[]
        scenes = manifest.get('scenes', [])
        query_probe = manifest.get("query_probe") if isinstance(manifest, dict) else None
        total_candidates = 0
        video_candidates = 0
        image_candidates = 0
        scenes_with_candidates = 0
        scenes_without_candidates = 0

        by_source = {"archive_org": 0, "wikimedia": 0, "europeana": 0, "other": 0}

        def _infer_source(candidate: dict) -> str:
            try:
                aid = str(candidate.get("archive_item_id") or "").strip()
                if ":" in aid:
                    prefix = aid.split(":", 1)[0].strip().lower()
                    # normalize common aliases
                    if prefix in ("archive", "archiveorg", "archive_org", "archive.org"):
                        return "archive_org"
                    if prefix in ("wikimedia", "commons", "wikimedia_commons"):
                        return "wikimedia"
                    if prefix in ("europeana",):
                        return "europeana"
                    return prefix or "other"
                # legacy (no prefix) => archive_org
                return "archive_org"
            except Exception:
                return "other"

        for scene in scenes:
            if not isinstance(scene, dict):
                continue

            beats = scene.get("visual_beats")
            if not isinstance(beats, list):
                beats = []

            scene_has_any = False
            for beat in beats:
                if not isinstance(beat, dict):
                    continue
                cands = beat.get("asset_candidates")
                if not isinstance(cands, list):
                    continue
                if cands:
                    scene_has_any = True

                for a in cands:
                    if not isinstance(a, dict):
                        continue
                    total_candidates += 1
                    mt = str(a.get("media_type") or "").strip().lower()
                    src = _infer_source(a)
                    if src not in by_source:
                        by_source["other"] += 1
                    else:
                        by_source[src] += 1
                    if mt == "video":
                        video_candidates += 1
                    elif mt == "image":
                        image_candidates += 1

            if scene_has_any:
                scenes_with_candidates += 1
            else:
                scenes_without_candidates += 1
        
        return jsonify({
            'success': True,
            'stats': {
                'total_candidates': total_candidates,
                'video_candidates': video_candidates,
                'image_candidates': image_candidates,
                'scenes_with_candidates': scenes_with_candidates,
                'scenes_without_candidates': scenes_without_candidates,
                'total_scenes': len(scenes),
                'manifest_exists': True,
                'manifest_path': manifest_path,
                'by_source': by_source,
                'query_probe': query_probe if isinstance(query_probe, dict) else None,
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'stats': {
                'manifest_exists': False
            }
        }), 500


@app.route('/api/video/visual-candidates/<episode_id>', methods=['GET', 'OPTIONS'])
def get_visual_candidates(episode_id):
    """
    Vrátí kandidáty pro vizuál (per scene/beat) včetně náhledů (thumbnail_url),
    aby UI i budoucí LLM Visual Assistant mohly dělat kvalitní výběr.
    Čte z archive_manifest.json (AAR output) a doplní thumbnail URL podle zdroje.
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'GET')
        return response

    try:
        from project_store import ProjectStore
        import json as json_lib
        import requests as req

        store = ProjectStore(PROJECTS_FOLDER)
        episode_dir = store.episode_dir(episode_id)
        manifest_path = os.path.join(episode_dir, 'archive_manifest.json')
        state_path = os.path.join(episode_dir, 'script_state.json')

        if not os.path.exists(manifest_path):
            return jsonify({
                "success": False,
                "error": "Archive manifest neexistuje - spusťte nejdřív Preview Videa (AAR).",
            }), 404

        with open(manifest_path, "r") as f:
            manifest = json_lib.load(f)

        # Load script_state (optional) to get full narration text per block_id
        state = {}
        if os.path.exists(state_path):
            try:
                with open(state_path, "r") as sf:
                    state = json_lib.load(sf) or {}
            except Exception:
                state = {}

        # Build block_id -> text lookup
        block_text = {}
        try:
            tts_pkg = None
            if isinstance(state.get("metadata"), dict) and isinstance(state["metadata"].get("tts_ready_package"), dict):
                tts_pkg = state["metadata"]["tts_ready_package"]
            elif isinstance(state.get("tts_ready_package"), dict):
                tts_pkg = state.get("tts_ready_package")
            if isinstance(tts_pkg, dict):
                blocks = tts_pkg.get("narration_blocks")
                if isinstance(blocks, list):
                    for b in blocks:
                        if not isinstance(b, dict):
                            continue
                        bid = str(b.get("block_id") or "").strip()
                        txt = str(b.get("text_tts") or b.get("text") or "").strip()
                        if bid and txt:
                            block_text[bid] = txt
        except Exception:
            pass

        def _split_source(aid: str) -> tuple[str, str]:
            s = str(aid or "").strip()
            if ":" in s:
                p, r = s.split(":", 1)
                p = p.strip().lower()
                r = r.strip()
                if p in ("archive", "archiveorg", "archive_org", "archive.org"):
                    return "archive_org", r
                if p in ("wikimedia", "commons", "wikimedia_commons"):
                    return "wikimedia", r
                if p in ("europeana",):
                    return "europeana", r
                return p or "other", r
            return "archive_org", s

        # Lightweight caches to avoid repeated API calls
        wm_cache = {}
        eu_cache = {}

        def _wm_thumb(file_id: str) -> str:
            fid = str(file_id or "").strip()
            if not fid:
                return ""
            fid = fid.replace("File:", "").replace(" ", "_")
            if fid in wm_cache:
                return wm_cache[fid] or ""
            try:
                api_url = "https://commons.wikimedia.org/w/api.php"
                params = {
                    "action": "query",
                    "format": "json",
                    "titles": f"File:{fid}",
                    "prop": "imageinfo",
                    "iiprop": "url",
                    "iiurlwidth": 360,
                }
                headers = {"User-Agent": "PodcastVideoBot/1.0 (Documentary preview; contact: local)"}
                r = req.get(api_url, params=params, headers=headers, timeout=15, verify=False)
                r.raise_for_status()
                data = r.json() or {}
                pages = (data.get("query") or {}).get("pages") or {}
                for _pid, page in pages.items():
                    if not isinstance(page, dict):
                        continue
                    ii = page.get("imageinfo")
                    if isinstance(ii, list) and ii and isinstance(ii[0], dict):
                        thumb = str(ii[0].get("thumburl") or ii[0].get("url") or "").strip()
                        wm_cache[fid] = thumb
                        return thumb
            except Exception:
                pass
            wm_cache[fid] = ""
            return ""

        def _eu_thumb(record_id: str) -> str:
            rid = str(record_id or "").strip().lstrip("/")
            if not rid:
                return ""
            if rid in eu_cache:
                return eu_cache[rid] or ""
            try:
                wskey = (os.getenv("EUROPEANA_API_KEY") or "").strip()
                if not wskey:
                    eu_cache[rid] = ""
                    return ""
                api_url = f"https://api.europeana.eu/record/v2/{rid}.json"
                params = {"wskey": wskey, "profile": "rich"}
                r = req.get(api_url, params=params, timeout=20, verify=False)
                r.raise_for_status()
                data = r.json() or {}
                obj = data.get("object") if isinstance(data.get("object"), dict) else {}
                prev = obj.get("edmPreview")
                if isinstance(prev, list) and prev:
                    eu_cache[rid] = str(prev[0] or "").strip()
                    return eu_cache[rid]
                if isinstance(prev, str) and prev.strip():
                    eu_cache[rid] = prev.strip()
                    return eu_cache[rid]
            except Exception:
                pass
            eu_cache[rid] = ""
            return ""

        def _thumb_for(aid: str) -> tuple[str, str]:
            src, raw = _split_source(aid)
            if src == "archive_org":
                return src, f"https://archive.org/services/img/{raw}"
            if src == "wikimedia":
                return src, _wm_thumb(raw)
            if src == "europeana":
                return src, _eu_thumb(raw)
            return src, ""

        assistant_metadata = manifest.get("_visual_assistant_metadata")
        if not isinstance(assistant_metadata, dict):
            assistant_metadata = None

        scenes_out = []
        for scene in (manifest.get("scenes") or []):
            if not isinstance(scene, dict):
                continue
            scene_id = str(scene.get("scene_id") or "").strip()
            # Map scene assets by id for join
            assets = scene.get("assets") if isinstance(scene.get("assets"), list) else []
            by_id = {}
            for a in assets:
                if isinstance(a, dict) and a.get("archive_item_id"):
                    by_id[str(a.get("archive_item_id"))] = a

            beats_out = []
            for beat in (scene.get("visual_beats") or []):
                if not isinstance(beat, dict):
                    continue
                bid = str(beat.get("block_id") or "").strip()
                cands = beat.get("asset_candidates") if isinstance(beat.get("asset_candidates"), list) else []
                cand_out = []
                for c in cands[:8]:
                    if not isinstance(c, dict):
                        continue
                    aid = str(c.get("archive_item_id") or "").strip()
                    if not aid:
                        continue
                    ainfo = by_id.get(aid, {})
                    src, thumb = _thumb_for(aid)
                    cand_out.append({
                        "archive_item_id": aid,
                        "source": src,
                        "thumbnail_url": thumb,
                        "title": (ainfo.get("title") or "")[:160] if isinstance(ainfo, dict) else "",
                        "description": (ainfo.get("description") or "")[:400] if isinstance(ainfo, dict) else "",
                        "asset_url": (ainfo.get("asset_url") or "") if isinstance(ainfo, dict) else "",
                        "score": c.get("score"),
                        "query_used": c.get("query_used"),
                        "source_query": (ainfo.get("_source_query") or "") if isinstance(ainfo, dict) else "",
                        "priority": c.get("priority"),
                        "media_type": c.get("media_type"),
                        "_visual_analysis": c.get("_visual_analysis") if isinstance(c.get("_visual_analysis"), dict) else None,
                    })

                beats_out.append({
                    "block_id": bid,
                    "block_index": beat.get("block_index"),
                    "selected_asset_id": beat.get("selected_asset_id") or "",
                    "text": block_text.get(bid) or beat.get("text_preview") or "",
                    "keywords": beat.get("keywords") if isinstance(beat.get("keywords"), list) else [],
                    "candidates": cand_out,
                })

            scenes_out.append({
                "scene_id": scene_id,
                "search_queries": scene.get("search_queries") if isinstance(scene.get("search_queries"), list) else [],
                "beats": beats_out,
            })

        return jsonify({
            "success": True,
            "episode_id": episode_id,
            "manifest_path": manifest_path,
            "assistant_metadata": assistant_metadata,
            "scenes": scenes_out,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/video/manifest/select-asset/<episode_id>', methods=['POST', 'OPTIONS'])
def select_manifest_asset(episode_id):
    """
    Persist a user's choice of the best visual candidate for a given beat into archive_manifest.json.
    This enables manual curation after Preview / LLM Visual Assistant.

    Body:
      - scene_id: str
      - block_id: str
      - archive_item_id: str | null  (null/empty clears selection)
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST,OPTIONS')
        return response

    try:
        from project_store import ProjectStore
        import json as json_lib

        episode_id = (episode_id or '').strip()
        if not episode_id:
            return jsonify({'success': False, 'error': 'episode_id je povinné'}), 400

        data = request.get_json() or {}
        scene_id = str(data.get("scene_id") or "").strip()
        block_id = str(data.get("block_id") or "").strip()
        archive_item_id = data.get("archive_item_id", "")
        archive_item_id = str(archive_item_id or "").strip()

        if not scene_id or not block_id:
            return jsonify({'success': False, 'error': 'scene_id a block_id jsou povinné'}), 400

        store = ProjectStore(PROJECTS_FOLDER)
        episode_dir = store.episode_dir(episode_id)
        manifest_path = os.path.join(episode_dir, 'archive_manifest.json')
        if not os.path.exists(manifest_path):
            return jsonify({'success': False, 'error': 'archive_manifest.json nenalezen - spusťte nejdřív Preview Videa'}), 404

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json_lib.load(f) or {}

        updated = False
        for sc in (manifest.get("scenes") or []):
            if not isinstance(sc, dict):
                continue
            if str(sc.get("scene_id") or "").strip() != scene_id:
                continue
            for beat in (sc.get("visual_beats") or []):
                if not isinstance(beat, dict):
                    continue
                if str(beat.get("block_id") or "").strip() != block_id:
                    continue
                if archive_item_id:
                    beat["selected_asset_id"] = archive_item_id
                    # Optional UX: move selected candidate to front
                    cands = beat.get("asset_candidates")
                    if isinstance(cands, list) and cands:
                        # Stable move-to-front for matching archive_item_id
                        chosen = []
                        rest = []
                        for c in cands:
                            if isinstance(c, dict) and str(c.get("archive_item_id") or "").strip() == archive_item_id:
                                chosen.append(c)
                            else:
                                rest.append(c)
                        if chosen:
                            beat["asset_candidates"] = chosen + rest
                else:
                    if "selected_asset_id" in beat:
                        beat.pop("selected_asset_id", None)
                updated = True
                break
            break

        if not updated:
            return jsonify({'success': False, 'error': 'Beat nenalezen v manifestu (scene_id/block_id)'}), 404

        with open(manifest_path, "w", encoding="utf-8") as f:
            json_lib.dump(manifest, f, ensure_ascii=False, indent=2)

        return jsonify({'success': True, 'episode_id': episode_id, 'scene_id': scene_id, 'block_id': block_id, 'selected_asset_id': archive_item_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/video/compile', methods=['POST', 'OPTIONS'])
def compile_video():
    """
    Video Compilation endpoint - spustí AAR + CB pro daný episode.
    Podporuje i rychlý remix hudby (jen CB) bez znovu-resolving assetů.
    
    Input:
    - episode_id: ID projektu
    - mode (optional): "full" (default) | "cb_only" | "aar_only"
    - music_bg_gain_db (optional): hlasitost hudebního podkresu v dB (např. -24). Uloží se do script_state a použije se při mixu.
    
    Modes:
    - "full": spustí AAR + CB (default)
    - "cb_only": spustí jen CB (rychlý remix bez nového hledání assetů)
    - "aar_only": spustí jen AAR (preview - najde videa bez stahování/kompilace)
    
    Output:
    - success: bool
    - video_path: cesta k vygenerovanému videu (pokud CB běžel)
    - metadata: info o kompilaci
    """
    # #region agent log (CRITICAL: Log every call to detect automatic triggers)
    try:
        import time as _time, json as _json, traceback
        data = request.get_json() or {}
        episode_id = str(data.get('episode_id') or '').strip()
        mode = str(data.get('mode') or 'full').strip()
        
        with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
            _f.write(_json.dumps({
                "sessionId": "debug-session",
                "runId": "CRITICAL",
                "hypothesisId": "AUTO_COMPILE_BUG",
                "location": "backend/app.py:compile_video",
                "message": "⚠️ COMPILE ENDPOINT CALLED",
                "data": {
                    "episode_id": episode_id,
                    "mode": mode,
                    "method": request.method,
                    "referrer": request.referrer,
                    "user_agent": request.headers.get('User-Agent', '')[:100],
                    "stack_trace": "".join(traceback.format_stack()[-5:])[:500],
                },
                "timestamp": int(_time.time() * 1000),
            }) + "\n")
    except Exception:
        pass
    # #endregion
    
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response
    
    try:
        from script_pipeline import _run_asset_resolver, _run_compilation_builder
        from project_store import ProjectStore
        import json as json_lib
        
        data = request.get_json() or {}
        episode_id = (data.get('episode_id') or '').strip()
        mode = (data.get('mode') or 'full').strip().lower()
        requested_music_bg_gain_db = data.get("music_bg_gain_db", None)

        # #region agent log (hypothesis C)
        try:
            import time as _time
            import json as _json
            # NOTE: do not log secrets/keys/PII
            with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
                _f.write(_json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "C",
                    "location": "backend/app.py:compile_video",
                    "message": "compile_video called",
                    "data": {
                        "episode_id": episode_id,
                        "mode": mode,
                        "has_body": bool(data),
                        "has_music_bg_gain_db": requested_music_bg_gain_db is not None,
                    },
                    "timestamp": int(_time.time() * 1000),
                }) + "\n")
        except Exception:
            pass
        # #endregion
        
        if not episode_id:
            return jsonify({'success': False, 'error': 'episode_id je povinný'}), 400
        
        # Load state
        store = ProjectStore(PROJECTS_FOLDER)
        state_path = os.path.join(store.episode_dir(episode_id), 'script_state.json')
        
        if not os.path.exists(state_path):
            return jsonify({'success': False, 'error': f'Projekt {episode_id} neexistuje'}), 404
        
        with open(state_path, 'r') as f:
            state = json_lib.load(f)
        
        # Check prerequisites
        if not state.get('shot_plan'):
            return jsonify({'success': False, 'error': 'Shot plan není dostupný - spusťte nejdřív FDA'}), 400

        # Require voiceover to avoid silent video
        try:
            voiceover_dir = os.path.join(store.episode_dir(episode_id), "voiceover")
            tts_files = state.get("tts_generated_files") or []
            has_voiceover = False
            if isinstance(tts_files, list) and any(isinstance(x, str) for x in tts_files):
                has_voiceover = True
            if not has_voiceover and os.path.exists(voiceover_dir):
                has_voiceover = any(f.endswith(".mp3") for f in os.listdir(voiceover_dir))
            # Legacy migration (from uploads/Narrator_*.mp3) if counts match narration_blocks
            if not has_voiceover:
                try:
                    expected = len(state.get("tts_ready_package", {}).get("narration_blocks", []) or [])
                    legacy = sorted([
                        f for f in os.listdir(UPLOAD_FOLDER)
                        if f.startswith("Narrator_") and f.endswith(".mp3")
                    ])
                    if expected > 0 and len(legacy) == expected:
                        os.makedirs(voiceover_dir, exist_ok=True)
                        import shutil
                        migrated = []
                        for f in legacy:
                            shutil.copy2(os.path.join(UPLOAD_FOLDER, f), os.path.join(voiceover_dir, f))
                            migrated.append(f)
                        state["tts_generated_files"] = migrated
                        state["tts_generated_dir"] = voiceover_dir
                        state["tts_generated_count"] = len(migrated)
                        project_store.write_script_state(episode_id, state)
                        has_voiceover = True
                except Exception as e:
                    print(f"⚠️ compile_video: legacy voiceover migration failed: {e}")

            if not has_voiceover:
                return jsonify({
                    'success': False,
                    'error': 'Voice-over není k dispozici. Nejdřív klikněte na „Vygenerovat Voice-over“.',
                    'hint': f'Očekávám MP3 v {voiceover_dir}'
                }), 400
        except Exception:
            # If check fails unexpectedly, still refuse silently-less compilation
            return jsonify({'success': False, 'error': 'Nelze ověřit voice-over soubory. Zkuste znovu vygenerovat Voice-over.'}), 400
        
        # Run compilation in thread (async)
        # Farm-proof: prevent concurrent compiles for the same episode (would stomp temp files and state writes).
        import threading
        _compile_locks = app.config.setdefault("_compile_locks", {})
        _compile_locks_guard = app.config.setdefault("_compile_locks_guard", threading.Lock())
        with _compile_locks_guard:
            ep_lock = _compile_locks.get(episode_id)
            if ep_lock is None:
                ep_lock = threading.Lock()
                _compile_locks[episode_id] = ep_lock

        if not ep_lock.acquire(blocking=False):
            return jsonify({
                "success": False,
                "error": "Kompilace pro tento projekt už běží. Počkejte prosím na dokončení.",
                "episode_id": episode_id,
            }), 409

        # Persist optional background music gain (so CB can read it from script_state).
        if requested_music_bg_gain_db is not None:
            try:
                gain_db = float(requested_music_bg_gain_db)
                gain_db = max(-60.0, min(0.0, gain_db))
            except Exception:
                try:
                    ep_lock.release()
                except Exception:
                    pass
                return jsonify({
                    "success": False,
                    "error": "music_bg_gain_db musí být číslo (např. -24).",
                    "episode_id": episode_id,
                }), 400

            try:
                latest_state = store.read_script_state(episode_id)
            except Exception:
                latest_state = state
            latest_state["music_bg_gain_db"] = gain_db
            try:
                store.write_script_state(episode_id, latest_state)
                state = latest_state
            except Exception as e:
                print(f"⚠️ compile_video: failed to persist music_bg_gain_db: {e}")

        def run_compilation():
            try:
                # Reload freshest state inside the background thread to avoid stale snapshot overwrites.
                try:
                    fresh_state = store.read_script_state(episode_id)
                except Exception:
                    fresh_state = state

                if mode != 'cb_only':
                    # AAR
                    cache_dir = os.path.join(store.episode_dir(episode_id), 'archive_cache')
                    # Preview mode (aar_only) skips FDA validation for quick results
                    skip_validation = (mode == 'aar_only')
                    _run_asset_resolver(fresh_state, episode_id, store, cache_dir, skip_validation=skip_validation)
                else:
                    # Ensure manifest path exists for CB
                    if not fresh_state.get("archive_manifest_path"):
                        candidate = os.path.join(store.episode_dir(episode_id), 'archive_manifest.json')
                        if os.path.exists(candidate):
                            fresh_state["archive_manifest_path"] = candidate
                            try:
                                store.write_script_state(episode_id, fresh_state)
                            except Exception:
                                pass
                
                # CB (skip if aar_only mode - preview only)
                if mode != 'aar_only':
                    storage_dir = os.path.join(store.episode_dir(episode_id), 'assets')
                    output_dir = OUTPUT_FOLDER
                    _run_compilation_builder(fresh_state, episode_id, store, storage_dir, output_dir)
                
            except Exception as e:
                print(f"❌ Video compilation failed: {e}")
                import traceback
                traceback.print_exc()
            finally:
                try:
                    ep_lock.release()
                except Exception:
                    pass
        
        # Start in background thread
        thread = threading.Thread(target=run_compilation, daemon=True)
        thread.start()
        
        # User-friendly messages
        mode_messages = {
            'full': 'Video compilation started (AAR + CB)',
            'cb_only': 'Music remix started (CB only)',
            'aar_only': 'Archive preview started (AAR only - searching for videos/images)',
        }
        message = mode_messages.get(mode, 'Processing started')
        
        return jsonify({
            'success': True,
            'message': message,
            'episode_id': episode_id,
            'mode': mode,
            'note': 'Check /api/script/state/<episode_id> for progress'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/video/download/<filename>', methods=['GET'])
def download_video(filename):
    """
    Endpoint pro STAŽENÍ vygenerovaného videa (Content-Disposition: attachment).
    Pro přehrávání v prohlížeči použijte /api/video/stream/<filename>.
    """
    try:
        # Zabezpečení - pouze soubory z output folderu
        filename = secure_filename(filename)
        video_path = os.path.join(OUTPUT_FOLDER, filename)
        
        if not os.path.exists(video_path):
            return jsonify({'error': 'Video nebylo nalezeno'}), 404

        return send_file(
            video_path,
            as_attachment=True,
            download_name=filename,
            mimetype='video/mp4'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/video/stream/<filename>', methods=['GET'])
def stream_video(filename):
    """
    Endpoint pro PŘEHRÁNÍ vygenerovaného videa v prohlížeči (Content-Disposition: inline).
    """
    try:
        filename = secure_filename(filename)
        video_path = os.path.join(OUTPUT_FOLDER, filename)

        if not os.path.exists(video_path):
            return jsonify({'error': 'Video nebylo nalezeno'}), 404

        return send_file(
            video_path,
            as_attachment=False,
            mimetype='video/mp4'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================
# DEBUG: Logging diagnostics (temporary, for Cursor debug mode)
# ============================================================
@app.route('/api/debug/logging-status', methods=['GET'])
def debug_logging_status():
    """
    Debug endpoint to verify runtime environment + ability to write the Cursor debug log file.
    Never log secrets. Safe to keep temporarily during debug mode.
    """
    try:
        import os as _os
        import time as _time
        import json as _json
        target = "/Users/petrliesner/podcasts/.cursor/debug.log"
        target_dir = _os.path.dirname(target)
        payload = {
            "success": True,
            "server_file": __file__,
            "cwd": _os.getcwd(),
            "pid": _os.getpid(),
            "target": target,
            "target_dir_exists": _os.path.isdir(target_dir),
            "target_exists": _os.path.exists(target),
            "write_ok": False,
            "write_error": None,
            "timestamp": int(_time.time() * 1000),
        }
        try:
            _os.makedirs(target_dir, exist_ok=True)
            with open(target, "a", encoding="utf-8") as _f:
                _f.write(_json.dumps({
                    "sessionId": "debug-session",
                    "runId": "diag",
                    "hypothesisId": "Z",
                    "location": "backend/app.py:debug_logging_status",
                    "message": "diagnostic write",
                    "data": {"server_file": __file__},
                    "timestamp": int(_time.time() * 1000),
                }) + "\n")
            payload["write_ok"] = True
            payload["target_exists"] = _os.path.exists(target)
        except Exception as e:
            payload["write_error"] = f"{type(e).__name__}: {str(e)}"
        return jsonify(payload)
    except Exception as e:
        return jsonify({"success": False, "error": f"{type(e).__name__}: {str(e)}"}), 500


@app.route('/api/video/visual-assistant/<episode_id>', methods=['POST', 'OPTIONS'])
def run_visual_assistant_endpoint(episode_id):
    """
    Spustí Visual Assistant (LLM Vision) pro reranking kandidátů v archive_manifest.json.
    
    POST body (JSON):
    {
      "model": "gpt-4o",  // optional, default z config
      "temperature": 0.3,  // optional
      "custom_prompt": "",  // optional
      "max_analyze_per_beat": 5  // optional
    }
    
    Returns:
    {
      "success": true,
      "message": "Visual Assistant finished",
      "total_beats": 24,
      "total_analyzed": 120,
      "manifest_path": "..."
    }
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response
    
    try:
        # Get config from request or use defaults
        data = request.get_json() or {}
        model = data.get('model', 'gpt-4o')
        temperature = data.get('temperature', 0.3)
        custom_prompt = data.get('custom_prompt')  # optional
        max_analyze_per_beat = data.get('max_analyze_per_beat', 5)
        
        # Get API key - prefer OpenRouter, fallback to OpenAI
        openrouter_key = os.getenv('OPENROUTER_API_KEY')
        openai_key = os.getenv('OPENAI_API_KEY')
        
        if openrouter_key:
            api_key = openrouter_key
            provider = "openrouter"
        elif openai_key:
            api_key = openai_key
            provider = "openai"
        else:
            return jsonify({
                'success': False,
                'error': 'API klíč není nastaven. Nastavte OPENROUTER_API_KEY nebo OPENAI_API_KEY v backend/.env a restartujte backend.'
            }), 500
        
        # Check if archive_manifest exists
        store = ProjectStore(PROJECTS_FOLDER)
        episode_dir = store.episode_dir(episode_id)
        manifest_path = os.path.join(episode_dir, 'archive_manifest.json')
        
        if not os.path.exists(manifest_path):
            return jsonify({
                'success': False,
                'error': 'Archive manifest nenalezen. Nejdřív spusťte „Preview Videa“ (AAR).'
            }), 404
        
        # Run Visual Assistant
        print(f"🎨 Running Visual Assistant for episode {episode_id}...")
        print(f"   Provider: {provider}, Model: {model}, Temperature: {temperature}")
        
        result_manifest = run_visual_assistant(
            episode_id=episode_id,
            projects_dir=PROJECTS_FOLDER,
            api_key=api_key,
            model=model,
            temperature=temperature,
            custom_prompt=custom_prompt,
            max_analyze_per_beat=max_analyze_per_beat,
            verbose=True,
            provider=provider
        )
        
        metadata = result_manifest.get('_visual_assistant_metadata', {})
        
        return jsonify({
            'success': True,
            'message': 'Visual Assistant finished',
            'total_beats': metadata.get('total_beats', 0),
            'total_analyzed': metadata.get('total_candidates_analyzed', 0),
            'manifest_path': manifest_path
        })
        
    except FileNotFoundError as e:
        return jsonify({'success': False, 'error': str(e)}), 404
    except Exception as e:
        print(f"❌ Visual Assistant error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# TOPIC INTELLIGENCE ASSISTANT (USA/EN) - ISOLATED FEATURE
# ============================================================

@app.route('/api/topic-intel/profiles', methods=['GET'])
def get_topic_intel_profiles():
    """
    Get list of available channel profiles for Topic Intelligence.
    Read-only endpoint, profiles are stored in topic_intel_profiles.json
    """
    try:
        profiles_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'topic_intel_profiles.json')
        
        if not os.path.exists(profiles_path):
            # Return default profiles if file doesn't exist
            return jsonify({
                'success': True,
                'profiles': [
                    {'id': 'us_history_docs', 'name': 'US History Docs', 'content_type': 'history_docs'},
                    {'id': 'us_true_crime', 'name': 'US True Crime', 'content_type': 'true_crime'}
                ]
            })
        
        with open(profiles_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Return list with basic info (full profiles used internally)
        profiles_list = []
        for profile in data.get('profiles', []):
            profiles_list.append({
                'id': profile.get('id'),
                'name': profile.get('name'),
                'content_type': profile.get('content_type'),
                'style_notes': profile.get('style_notes', '')
            })
        
        return jsonify({
            'success': True,
            'profiles': profiles_list
        })
        
    except Exception as e:
        print(f"❌ Error loading profiles: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'profiles': [
                {'id': 'us_history_docs', 'name': 'US History Docs'},
                {'id': 'us_true_crime', 'name': 'US True Crime'}
            ]
        }), 200  # Return 200 with fallback profiles


@app.route('/api/topic-intel/research', methods=['POST', 'OPTIONS'])
def topic_intel_research():
    """
    Manual research trigger for Topic Intelligence Assistant.
    USA/EN only, no pipeline integration.
    
    Isolated feature: generates topic recommendations based on:
    - Wikipedia pageviews (demand signal)
    - YouTube competition analysis
    - Google Trends (placeholder for MVP)
    
    Request body:
    {
        "count": 20,  // 5-50
        "window_days": 7  // 7 or 30
    }
    
    Response:
    {
        "success": true,
        "request_id": "ti_abc123",
        "generated_at": "2026-01-01T12:00:00Z",
        "locale": "US",
        "language": "en-US",
        "items": [
            {
                "topic": "...",
                "rating_letter": "A++",
                "score_total": 94,
                "why_now": "...",
                "suggested_angle": "...",
                "signals": {...},
                "competition_flags": [...],
                "sources": [...]
            }
        ],
        "stats": {...}
    }
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response
    
    try:
        # Feature flag check
        feature_enabled = os.getenv('TOPIC_INTEL_ENABLED', 'false').lower()
        if feature_enabled not in ('true', '1', 'yes'):
            return jsonify({
                'success': False,
                'error': 'Topic Intelligence feature není povolena. Nastavte TOPIC_INTEL_ENABLED=true v backend/.env'
            }), 403
        
        # Parse request
        data = request.get_json() or {}
        count = int(data.get('count', 20))
        window_days = int(data.get('window_days', 7))
        profile_id = data.get('profile_id', 'us_history_docs')
        recommendation_mode = data.get('recommendation_mode', 'momentum')
        
        # LLM configuration (optional)
        llm_config = data.get('llm_config', {})
        provider = llm_config.get('provider', 'openrouter')
        model = llm_config.get('model', 'openai/gpt-4o')
        temperature = float(llm_config.get('temperature', 0.7))
        custom_prompt = llm_config.get('custom_prompt', None)
        
        # Validation
        if count < 5 or count > 50:
            return jsonify({
                'success': False,
                'error': 'Počet doporučení musí být mezi 5 a 50'
            }), 400
        
        if window_days not in (7, 30):
            return jsonify({
                'success': False,
                'error': 'Časové okno musí být 7 nebo 30 dní'
            }), 400
        
        if recommendation_mode not in ('momentum', 'balanced', 'evergreen'):
            return jsonify({
                'success': False,
                'error': 'Režim doporučení musí být momentum, balanced nebo evergreen'
            }), 400
        
        # Check OpenRouter API key (only provider supported)
        openrouter_key = os.getenv('OPENROUTER_API_KEY', '')
        if not openrouter_key:
            return jsonify({
                'success': False,
                'error': 'OpenRouter API klíč není nastaven. Nastavte OPENROUTER_API_KEY v backend/.env'
            }), 500
        
        # Import service (lazy import to avoid import errors if feature disabled)
        from topic_intel_service import TopicIntelService
        
        # Execute research
        print(f"🔬 Topic Intelligence: Starting research (profile={profile_id}, count={count}, window={window_days}d, mode={recommendation_mode}, model={model}, temp={temperature})")
        service = TopicIntelService(verbose=True)
        results = service.research(
            count=count,
            window_days=window_days,
            profile_id=profile_id,
            locale='US',
            language='en-US',
            llm_provider=provider,
            llm_model=model,
            llm_temperature=temperature,
            llm_custom_prompt=custom_prompt,
            recommendation_mode=recommendation_mode
        )
        
        print(f"✅ Topic Intelligence: Research complete (TOP: {results['stats']['top_recommendations']}, Other: {results['stats']['other_ideas']})")
        
        return jsonify({
            'success': True,
            'request_id': results['request_id'],
            'generated_at': results['generated_at'],
            'locale': results['locale'],
            'language': results['language'],
            'recommendation_mode': results['recommendation_mode'],
            'items': results['items'],
            'other_ideas': results['other_ideas'],
            'stats': results['stats']
        })
        
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f'Neplatné vstupní údaje: {str(e)}'
        }), 400
    except Exception as e:
        print(f"❌ Topic Intelligence error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'Chyba při research: {str(e)}'
        }), 500


# ════════════════════════════════════════════════════════════════════════════
# AAR STEP-BY-STEP API (User Control Over Query Generation → Search → LLM)
# ════════════════════════════════════════════════════════════════════════════

@app.route('/api/aar/step1-generate-queries/<episode_id>', methods=['POST', 'OPTIONS'])
def aar_step1_generate_queries(episode_id):
    """
    Step 1: Generate AAR queries from shot_plan (NO SEARCH).
    User can then edit/remove/add queries before proceeding to Step 2.
    
    Returns:
        {
            "success": bool,
            "queries": [str],
            "episode_topic": str,
            "query_count": int
        }
    """
    # #region agent log
    try:
        import time as _time, json as _json
        with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
            _f.write(_json.dumps({
                "sessionId": "debug-session", "runId": "aar-step1", "hypothesisId": "H1",
                "location": "backend/app.py:aar_step1_generate_queries",
                "message": "Endpoint called",
                "data": {"episode_id": str(episode_id), "method": request.method},
                "timestamp": int(_time.time() * 1000),
            }) + "\n")
    except Exception:
        pass
    # #endregion
    
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST,OPTIONS')
        return response
    
    try:
        from aar_step_by_step import generate_queries_for_episode
        
        # #region agent log
        try:
            import time as _time, json as _json
            with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
                _f.write(_json.dumps({
                    "sessionId": "debug-session", "runId": "aar-step1", "hypothesisId": "H4",
                    "location": "backend/app.py:aar_step1_generate_queries",
                    "message": "Import successful",
                    "data": {"project_store_available": 'project_store' in globals()},
                    "timestamp": int(_time.time() * 1000),
                }) + "\n")
        except Exception:
            pass
        # #endregion
        
        episode_id = (episode_id or '').strip()
        if not episode_id:
            return jsonify({'success': False, 'error': 'episode_id je povinné'}), 400
        
        result = generate_queries_for_episode(episode_id, project_store)
        
        # #region agent log
        try:
            import time as _time, json as _json
            with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
                _f.write(_json.dumps({
                    "sessionId": "debug-session", "runId": "aar-step1", "hypothesisId": "H1",
                    "location": "backend/app.py:aar_step1_generate_queries",
                    "message": "Success result",
                    "data": {"success": result.get('success'), "query_count": len(result.get('queries', []))},
                    "timestamp": int(_time.time() * 1000),
                }) + "\n")
        except Exception:
            pass
        # #endregion
        
        return jsonify(result)
    
    except Exception as e:
        # #region agent log
        try:
            import time as _time, json as _json, traceback
            with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
                _f.write(_json.dumps({
                    "sessionId": "debug-session", "runId": "aar-step1", "hypothesisId": "H3-H4",
                    "location": "backend/app.py:aar_step1_generate_queries",
                    "message": "Exception caught",
                    "data": {"error": str(e), "error_type": type(e).__name__, "traceback": traceback.format_exc()[:500]},
                    "timestamp": int(_time.time() * 1000),
                }) + "\n")
        except Exception:
            pass
        # #endregion
        
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }), 500


@app.route('/api/aar/step2-search/<episode_id>', methods=['POST', 'OPTIONS'])
def aar_step2_search(episode_id):
    """
    Step 2: Search archives with user-edited queries (NO LLM YET).
    Returns raw search results.
    
    Input:
        {
            "queries": [str]  # User-edited list of queries
        }
    
    Returns:
        {
            "success": bool,
            "raw_video_candidates": [dict],
            "raw_image_candidates": [dict],
            "queries_executed": [str],
            "stats": {...}
        }
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST,OPTIONS')
        return response
    
    try:
        from aar_step_by_step import search_with_custom_queries
        
        episode_id = (episode_id or '').strip()
        if not episode_id:
            return jsonify({'success': False, 'error': 'episode_id je povinné'}), 400
        
        data = request.get_json() or {}
        custom_queries = data.get('queries') or []
        
        if not custom_queries or not isinstance(custom_queries, list):
            return jsonify({'success': False, 'error': 'queries (list) je povinné'}), 400

        # #region agent log
        try:
            import time as _time, json as _json, os as _os
            with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
                _f.write(_json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "H4",
                    "location": "backend/app.py:aar_step2_search",
                    "message": "Step2 search called",
                    "data": {
                        "episode_id": str(episode_id),
                        "query_count": int(len(custom_queries)),
                        "first_query": str(custom_queries[0])[:160] if custom_queries else "",
                        "has_europeana_key": bool(str(_os.getenv("EUROPEANA_API_KEY") or "").strip()),
                        "aar_multi_source_mode": str(_os.getenv("AAR_MULTI_SOURCE_MODE") or ""),
                        "aar_multi_source_min_results": str(_os.getenv("AAR_MULTI_SOURCE_MIN_RESULTS_PER_QUERY") or ""),
                        "aar_multi_source_max_providers": str(_os.getenv("AAR_MULTI_SOURCE_MAX_PROVIDERS_PER_QUERY") or ""),
                    },
                    "timestamp": int(_time.time() * 1000),
                }) + "\n")
        except Exception:
            pass
        # #endregion
        
        result = search_with_custom_queries(episode_id, custom_queries, project_store, verbose=True)

        # #region agent log
        try:
            import time as _time, json as _json
            stats = result.get("stats") if isinstance(result, dict) else {}
            with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
                _f.write(_json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "H4",
                    "location": "backend/app.py:aar_step2_search",
                    "message": "Step2 search result summary",
                    "data": {
                        "success": bool(result.get("success")) if isinstance(result, dict) else None,
                        "total_video_candidates": int(stats.get("total_video_candidates") or 0) if isinstance(stats, dict) else None,
                        "total_image_candidates": int(stats.get("total_image_candidates") or 0) if isinstance(stats, dict) else None,
                    },
                    "timestamp": int(_time.time() * 1000),
                }) + "\n")
        except Exception:
            pass
        # #endregion

        return jsonify(result)
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }), 500


@app.route('/api/aar/step3-llm-check/<episode_id>', methods=['POST', 'OPTIONS'])
def aar_step3_llm_check(episode_id):
    """
    Step 3: Run LLM quality check on raw search results.
    Deduplicate + rank by relevance + quality.
    
    Returns:
        {
            "success": bool,
            "unique_videos": [dict],
            "unique_images": [dict],
            "selected_videos": [dict],
            "selected_images": [dict],
            "stats": {...}
        }
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST,OPTIONS')
        return response
    
    try:
        from aar_step_by_step import llm_quality_check
        
        episode_id = (episode_id or '').strip()
        if not episode_id:
            return jsonify({'success': False, 'error': 'episode_id je povinné'}), 400
        
        data = request.get_json() or {}
        manual_selection = data.get('manual_selection')  # Optional: {"video_ids": [str], "image_ids": [str]}

        # #region agent log
        try:
            import time as _time, json as _json
            with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
                _f.write(_json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "H5",
                    "location": "backend/app.py:aar_step3_llm_check",
                    "message": "Step3 LLM check called",
                    "data": {
                        "episode_id": str(episode_id),
                        "has_manual_selection": bool(manual_selection),
                        "manual_video_count": len(manual_selection.get("video_ids") or []) if manual_selection else 0,
                        "manual_image_count": len(manual_selection.get("image_ids") or []) if manual_selection else 0,
                    },
                    "timestamp": int(_time.time() * 1000),
                }) + "\n")
        except Exception:
            pass
        # #endregion
        
        result = llm_quality_check(episode_id, project_store, manual_selection=manual_selection, verbose=True)

        # #region agent log
        try:
            import time as _time, json as _json
            stats = result.get("stats") if isinstance(result, dict) else {}
            with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
                _f.write(_json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "H5",
                    "location": "backend/app.py:aar_step3_llm_check",
                    "message": "Step3 LLM check result summary",
                    "data": {
                        "success": bool(result.get("success")) if isinstance(result, dict) else None,
                        "pool_videos": int(stats.get("pool_videos") or 0) if isinstance(stats, dict) else None,
                        "pool_images": int(stats.get("pool_images") or 0) if isinstance(stats, dict) else None,
                    },
                    "timestamp": int(_time.time() * 1000),
                }) + "\n")
        except Exception:
            pass
        # #endregion

        return jsonify(result)
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 50000))
    print(f"🌐 Server běží na: http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False, load_dotenv=False)

