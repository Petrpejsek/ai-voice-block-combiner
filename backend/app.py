from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from pydub import AudioSegment
import os
import json
import uuid
from datetime import datetime, timedelta
import re
import subprocess
import tempfile
import requests
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from gpt_utils import call_openai, create_narration_prompt

# Načte environment variables z .env souboru
load_dotenv()

app = Flask(__name__)
CORS(app)  # Povolí komunikaci s frontend aplikací

# Složky pro soubory
UPLOAD_FOLDER = '../uploads'
OUTPUT_FOLDER = '../output'
BACKGROUNDS_FOLDER = '../uploads/backgrounds'
VIDEO_BACKGROUNDS_FOLDER = '../uploads/video_backgrounds'
PROJECTS_FOLDER = '../projects'

# Vytvoří složky pokud neexistují
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(BACKGROUNDS_FOLDER, exist_ok=True)
os.makedirs(VIDEO_BACKGROUNDS_FOLDER, exist_ok=True)
os.makedirs(PROJECTS_FOLDER, exist_ok=True)

# Povolené typy obrázků pro pozadí
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg'}
# Povolené typy videí pro pozadí
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'mov'}

def allowed_image_file(filename):
    """
    Kontrola, zda je soubor povolený obrázek
    """
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

def allowed_video_file(filename):
    """
    Kontrola, zda je soubor povolené video
    """
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_VIDEO_EXTENSIONS

def natural_sort_key(filename):
    """
    Tato funkce umožní správné řazení souborů podle čísel v názvu
    Například: Tesla_1.mp3, Tesla_2.mp3, Tesla_10.mp3
    """
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', filename)]

def generate_voice_with_elevenlabs(text, voice_id, api_key, filename):
    """
    Generuje hlasový soubor pomocí ElevenLabs API
    """
    try:
        # ElevenLabs API endpoint
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        
        # Headers pro API request
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": api_key
        }
        
        # Data pro generování hlasu
        data = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.5,
                "style": 0.0,
                "use_speaker_boost": True
            }
        }
        
        print(f"🎤 Generuji hlas pro: {filename}")
        print(f"📝 Text: {text[:100]}...")
        
        # Volání ElevenLabs API
        response = requests.post(url, json=data, headers=headers, timeout=30)
        
        if response.status_code == 200:
            # Uloží audio soubor
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            with open(file_path, 'wb') as f:
                f.write(response.content)
            
            print(f"✅ Hlas úspěšně vygenerován: {filename}")
            return True, f"Hlas úspěšně vygenerován: {filename}"
        else:
            error_msg = f"ElevenLabs API chyba: {response.status_code} - {response.text}"
            print(f"❌ {error_msg}")
            return False, error_msg
            
    except requests.exceptions.Timeout:
        error_msg = "Časový limit API volání byl překročen"
        print(f"❌ {error_msg}")
        return False, error_msg
    except Exception as e:
        error_msg = f"Neočekávaná chyba při generování hlasu: {str(e)}"
        print(f"❌ {error_msg}")
        return False, error_msg

def generate_voice_with_agent(text, agent_id, api_key, filename):
    """
    Převede agent_id na voice_id a použije klasické TTS (bez komplikací)
    """
    print(f"🤖 Převádím agent_id na voice_id pro: {filename}")
    
    # JEDNODUCHÉ MAPOVÁNÍ - žádné fallbacky, žádné komplikace
    agent_to_voice = {
        "agent_01jysnj4zgfqgsncz1ww8t6eyd": "pNInz6obpgDQGcFmaJgB",  # Tesla -> Adam
        "agent_01jysp1gvmfe8s696kdhbmgzg8": "21m00Tcm4TlvDq8ikWAM",  # Socrates -> Rachel
    }
    
    voice_id = agent_to_voice.get(agent_id, "pNInz6obpgDQGcFmaJgB")  # Default Adam
    print(f"✅ Používám voice_id: {voice_id}")
    
    # Použije spolehlivé klasické TTS
    return generate_voice_with_elevenlabs(text, voice_id, api_key, filename)

def generate_srt_content(audio_segments_info, subtitle_data):
    """
    Generuje obsah .srt souboru z informací o audio segmentech
    """
    def format_timedelta_for_srt(td):
        """Konvertuje timedelta na správný SRT formát HH:MM:SS,mmm"""
        total_seconds = int(td.total_seconds())
        milliseconds = int(td.microseconds / 1000)
        
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
    
    srt_content = []
    current_time = timedelta(0)
    
    for i, segment_info in enumerate(audio_segments_info, 1):
        filename = segment_info['filename']
        duration = segment_info['duration']
        
        # Najde text pro tento soubor
        text = subtitle_data.get(filename, f"Audio block {i}")
        
        # Čas začátku a konce
        start_time = current_time
        end_time = current_time + timedelta(milliseconds=duration)
        
        # Správný formát času pro SRT (HH:MM:SS,mmm)
        start_str = format_timedelta_for_srt(start_time)
        end_str = format_timedelta_for_srt(end_time)
        
        # Přidá SRT blok
        srt_content.append(f"{i}")
        srt_content.append(f"{start_str} --> {end_str}")
        srt_content.append(text)
        srt_content.append("")  # Prázdný řádek
        
        # Aktualizuje čas pro další segment (včetně pauzy)
        current_time = end_time + timedelta(milliseconds=segment_info.get('pause_after', 0))
    
    return '\n'.join(srt_content)

def generate_video_with_waveform(audio_file_path, srt_file_path, output_video_path):
    """
    Generuje MP4 video s waveform vizualizací a titulky pomocí ffmpeg
    """
    try:
        # Základní ffmpeg příkaz pro vytvoření videa s waveform a titulky
        cmd = [
            'ffmpeg',
            '-y',  # Přepíše výstupní soubor pokud existuje
            '-i', audio_file_path,  # Input audio soubor
            '-filter_complex',
            '[0:a]showwaves=s=1920x1080:mode=line:colors=0x3b82f6:rate=30,format=yuv420p[v]',
            '-map', '[v]',  # Mapuje video stream
            '-map', '0:a',  # Mapuje audio stream
            '-c:v', 'libx264',  # Video kodek
            '-c:a', 'aac',      # Audio kodek
            '-preset', 'medium', # Kvalita/rychlost komprese
            '-crf', '23',       # Konstanta kvalita
            '-r', '30',         # Frame rate
            output_video_path
        ]
        
        # Spustí ffmpeg příkaz s prodlouženým timeoutem pro dlouhé audio soubory
        print(f"🎬 Generuji video s waveform: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        
        if result.returncode != 0:
            print(f"❌ Chyba při generování videa: {result.stderr}")
            return False, f"FFmpeg chyba: {result.stderr}"
        
        # Pokud existuje SRT soubor, přidá titulky jako druhý krok
        if srt_file_path and os.path.exists(srt_file_path):
            temp_video = output_video_path + '.temp.mp4'
            os.rename(output_video_path, temp_video)
            
            cmd_subtitles = [
                'ffmpeg',
                '-y',
                '-i', temp_video,
                '-vf', f'subtitles={srt_file_path}:force_style=\'FontSize=16,PrimaryColour=&Hffffff,OutlineColour=&H000000,Outline=2,Shadow=1\'',
                '-c:a', 'copy',  # Kopíruje audio bez re-enkódování
                output_video_path
            ]
            
            print(f"📝 Přidávám titulky: {' '.join(cmd_subtitles)}")
            result = subprocess.run(cmd_subtitles, capture_output=True, text=True, timeout=600)
            
            # Smaže dočasný soubor
            if os.path.exists(temp_video):
                os.remove(temp_video)
            
            if result.returncode != 0:
                print(f"❌ Chyba při přidávání titulků: {result.stderr}")
                return False, f"FFmpeg chyba při titulcích: {result.stderr}"
        
        print(f"✅ Video úspěšně vygenerováno: {output_video_path}")
        return True, "Video úspěšně vygenerováno"
        
    except subprocess.TimeoutExpired:
        return False, "Časový limit pro generování videa byl překročen"
    except Exception as e:
        print(f"❌ Neočekávaná chyba při generování videa: {str(e)}")
        return False, f"Neočekávaná chyba: {str(e)}"

def generate_video_with_background(audio_file_path, background_image_path, srt_file_path, output_video_path):
    """
    Generuje MP4 video s obrázkem pozadí a titulky pomocí ffmpeg
    """
    try:
        # Základní ffmpeg příkaz pro vytvoření videa s obrázkem pozadí
        cmd = [
            'ffmpeg',
            '-y',  # Přepíše výstupní soubor pokud existuje
            '-loop', '1',  # Opakuje obrázek
            '-i', background_image_path,  # Input obrázek pozadí
            '-i', audio_file_path,  # Input audio soubor
            '-c:v', 'libx264',  # Video kodek
            '-c:a', 'aac',      # Audio kodek
            '-shortest',        # Ukončí video když skončí nejkratší stream (audio)
            '-preset', 'medium', # Kvalita/rychlost komprese
            '-crf', '23',       # Konstanta kvalita
            '-r', '30',         # Frame rate
            '-pix_fmt', 'yuv420p',  # Pixel formát pro kompatibilitu
            output_video_path
        ]
        
        # Spustí ffmpeg příkaz s prodlouženým timeoutem pro dlouhé audio soubory
        print(f"🎬 Generuji video s pozadím: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        
        if result.returncode != 0:
            print(f"❌ Chyba při generování videa: {result.stderr}")
            return False, f"FFmpeg chyba: {result.stderr}"
        
        # Pokud existuje SRT soubor, přidá titulky jako druhý krok
        if srt_file_path and os.path.exists(srt_file_path):
            temp_video = output_video_path + '.temp.mp4'
            os.rename(output_video_path, temp_video)
            
            cmd_subtitles = [
                'ffmpeg',
                '-y',
                '-i', temp_video,
                '-vf', f'subtitles={srt_file_path}:force_style=\'FontSize=16,PrimaryColour=&Hffffff,OutlineColour=&H000000,Outline=2,Shadow=1\'',
                '-c:a', 'copy',  # Kopíruje audio bez re-enkódování
                output_video_path
            ]
            
            print(f"📝 Přidávám titulky k videu s pozadím: {' '.join(cmd_subtitles)}")
            result = subprocess.run(cmd_subtitles, capture_output=True, text=True, timeout=600)
            
            # Smaže dočasný soubor
            if os.path.exists(temp_video):
                os.remove(temp_video)
            
            if result.returncode != 0:
                print(f"❌ Chyba při přidávání titulků: {result.stderr}")
                return False, f"FFmpeg chyba při titulcích: {result.stderr}"
        
        print(f"✅ Video s pozadím úspěšně vygenerováno: {output_video_path}")
        return True, "Video s pozadím úspěšně vygenerováno"
        
    except subprocess.TimeoutExpired:
        return False, "Časový limit pro generování videa byl překročen"
    except Exception as e:
        print(f"❌ Neočekávaná chyba při generování videa: {str(e)}")
        return False, f"Neočekávaná chyba: {str(e)}"

def generate_video_with_video_background(audio_file_path, background_video_path, srt_file_path, output_video_path):
    """
    Generuje MP4 video s video pozadím a titulky pomocí ffmpeg
    """
    try:
        # Základní ffmpeg příkaz pro vytvoření videa s video pozadím
        cmd = [
            'ffmpeg',
            '-y',  # Přepíše výstupní soubor pokud existuje
            '-stream_loop', '-1',  # Opakuje video pozadí nekonečně
            '-i', background_video_path,  # Input video pozadí
            '-i', audio_file_path,  # Input audio soubor
            '-c:v', 'libx264',  # Video kodek
            '-c:a', 'aac',      # Audio kodek
            '-shortest',        # Ukončí video když skončí nejkratší stream (audio)
            '-preset', 'medium', # Kvalita/rychlost komprese
            '-crf', '23',       # Konstanta kvalita
            '-r', '30',         # Frame rate
            '-pix_fmt', 'yuv420p',  # Pixel formát pro kompatibilitu
            output_video_path
        ]
        
        # Spustí ffmpeg příkaz s prodlouženým timeoutem pro dlouhé audio soubory
        print(f"🎥 Generuji video s video pozadím: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        
        if result.returncode != 0:
            print(f"❌ Chyba při generování videa: {result.stderr}")
            return False, f"FFmpeg chyba: {result.stderr}"
        
        # Pokud existuje SRT soubor, přidá titulky jako druhý krok
        if srt_file_path and os.path.exists(srt_file_path):
            temp_video = output_video_path + '.temp.mp4'
            os.rename(output_video_path, temp_video)
            
            cmd_subtitles = [
                'ffmpeg',
                '-y',
                '-i', temp_video,
                '-vf', f'subtitles={srt_file_path}:force_style=\'FontSize=16,PrimaryColour=&Hffffff,OutlineColour=&H000000,Outline=2,Shadow=1\'',
                '-c:a', 'copy',  # Kopíruje audio bez re-enkódování
                output_video_path
            ]
            
            print(f"📝 Přidávám titulky k videu s video pozadím: {' '.join(cmd_subtitles)}")
            result = subprocess.run(cmd_subtitles, capture_output=True, text=True, timeout=600)
            
            # Smaže dočasný soubor
            if os.path.exists(temp_video):
                os.remove(temp_video)
            
            if result.returncode != 0:
                print(f"❌ Chyba při přidávání titulků: {result.stderr}")
                return False, f"FFmpeg chyba při titulcích: {result.stderr}"
        
        print(f"✅ Video s video pozadím úspěšně vygenerováno: {output_video_path}")
        return True, "Video s video pozadím úspěšně vygenerováno"
        
    except subprocess.TimeoutExpired:
        return False, "Časový limit pro generování videa byl překročen"
    except Exception as e:
        print(f"❌ Neočekávaná chyba při generování videa: {str(e)}")
        return False, f"Neočekávaná chyba: {str(e)}"

@app.route('/api/upload', methods=['POST'])
def upload_files():
    """
    Endpoint pro nahrání souborů a jejich zpracování
    """
    try:
        # Získá parametry z formuláře
        pause_duration = float(request.form.get('pause_duration', 0.6)) * 1000  # Převede na milisekundy
        generate_subtitles = request.form.get('generate_subtitles') == 'true'
        generate_video = request.form.get('generate_video') == 'true'
        background_filename = request.form.get('background_filename')  # Obrázek pozadí pro video
        video_background_filename = request.form.get('video_background_filename')  # Video pozadí pro video
        subtitle_data = {}
        file_volumes = {}  # Slovník pro hlasitosti souborů (v dB)
        
        if generate_subtitles and 'subtitle_json' in request.form:
            subtitle_data = json.loads(request.form.get('subtitle_json'))
        
        # Načte nastavení hlasitosti souborů
        if 'file_volumes' in request.form:
            try:
                file_volumes = json.loads(request.form.get('file_volumes'))
                print(f"🔊 Nastavení hlasitosti: {file_volumes}")
                print(f"🔊 Typ hlasitostí: {[(k, type(v), v) for k, v in file_volumes.items()]}")
            except json.JSONDecodeError:
                print("⚠️ Neplatný JSON pro hlasitosti souborů")
                file_volumes = {}
        
        # Zpracuje nahrané soubory
        uploaded_files = request.files.getlist('audio_files')
        intro_file = request.files.get('intro_file')
        outro_file = request.files.get('outro_file')
        
        if not uploaded_files:
            return jsonify({'error': 'Nebyly nahrány žádné audio soubory'}), 400
        
        # Vytvoří seznam audio segmentů pro spojení
        audio_segments = []
        audio_segments_info = []
        
        # Přidá intro pokud existuje
        if intro_file and intro_file.filename:
            intro_path = os.path.join(UPLOAD_FOLDER, f"intro_{uuid.uuid4().hex}.mp3")
            intro_file.save(intro_path)
            intro_audio = AudioSegment.from_mp3(intro_path)
            audio_segments.append(intro_audio)
            audio_segments_info.append({
                'filename': 'intro.mp3',
                'duration': len(intro_audio),
                'pause_after': pause_duration
            })
            os.remove(intro_path)  # Smaže dočasný soubor
        
        # OPRAVA: Zachová pořadí souborů jak byly nahrány místo abecedního řazení
        # Seřadí a zpracuje hlavní audio soubory
        file_list = [(f.filename, f) for f in uploaded_files if f.filename]
        # ODSTRANĚNO: file_list.sort(key=lambda x: natural_sort_key(x[0]))
        # Zachová původní pořadí z frontendu
        
        for i, (filename, file) in enumerate(file_list):
            # Zkontroluje, jestli je to prázdný soubor (existující na serveru)
            if hasattr(file, 'content_length') and file.content_length == 0:
                # Existující soubor - načte přímo z uploads
                existing_path = os.path.join(UPLOAD_FOLDER, filename)
                if os.path.exists(existing_path):
                    print(f"📁 Používá existující soubor: {filename}")
                    
                    # OPRAVA: Zkontroluje a převede problematické MP3 soubory s timeoutem
                    try:
                        audio = AudioSegment.from_mp3(existing_path)
                    except Exception as e:
                        print(f"⚠️ Soubor {filename} je poškozený, pokouším se opravit...")
                        # Převede soubor pomocí FFmpeg s timeoutem
                        temp_fixed = existing_path + '_fixed.mp3'
                        cmd = ['ffmpeg', '-y', '-i', existing_path, '-acodec', 'libmp3lame', '-ab', '128k', temp_fixed]
                        
                        try:
                            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                            
                            if result.returncode == 0:
                                # Nahradí původní soubor opraveným
                                os.replace(temp_fixed, existing_path)
                                audio = AudioSegment.from_mp3(existing_path)
                                print(f"✅ Soubor {filename} úspěšně opraven")
                            else:
                                print(f"❌ Nelze opravit soubor {filename}: {result.stderr}")
                                return jsonify({'error': f'Soubor {filename} je poškozený a nelze ho opravit'}), 400
                        except subprocess.TimeoutExpired:
                            print(f"❌ Timeout při opravě souboru {filename}")
                            # Smaže případný částečně vytvořený soubor
                            if os.path.exists(temp_fixed):
                                os.remove(temp_fixed)
                            return jsonify({'error': f'Timeout při opravě souboru {filename}'}), 400
                else:
                    return jsonify({'error': f'Existující soubor {filename} nebyl nalezen na serveru'}), 400
            else:
                # Uloží nahraný soubor dočasně
                temp_path = os.path.join(UPLOAD_FOLDER, f"temp_{uuid.uuid4().hex}.mp3")
                file.save(temp_path)
                
                # Načte audio
                audio = AudioSegment.from_mp3(temp_path)
                
                # Smaže dočasný soubor
                os.remove(temp_path)
                print(f"📤 Zpracován nahraný soubor: {filename}")
            
            # Aplikuje nastavení hlasitosti pokud je definováno
            volume_adjustment = file_volumes.get(filename, 0)
            print(f"🔊 Soubor {filename}: nastavená hlasitost {volume_adjustment:+.1f}dB")
            if volume_adjustment != 0:
                audio = audio + volume_adjustment  # pydub používá + pro změnu hlasitosti v dB
                print(f"✅ Aplikována hlasitost {filename}: {volume_adjustment:+.1f}dB")
            else:
                print(f"⏸️ Bez změny hlasitosti pro {filename} (0dB)")
            
            audio_segments.append(audio)
            
            # Přidá informace o segmentu
            pause_after = pause_duration if i < len(file_list) - 1 else 0  # Bez pauzy po posledním
            audio_segments_info.append({
                'filename': filename,
                'duration': len(audio),
                'pause_after': pause_after
            })
        
        # Přidá outro pokud existuje
        if outro_file and outro_file.filename:
            outro_path = os.path.join(UPLOAD_FOLDER, f"outro_{uuid.uuid4().hex}.mp3")
            outro_file.save(outro_path)
            outro_audio = AudioSegment.from_mp3(outro_path)
            audio_segments.append(outro_audio)
            audio_segments_info.append({
                'filename': 'outro.mp3',
                'duration': len(outro_audio),
                'pause_after': 0
            })
            os.remove(outro_path)
        
        # Spojí všechny audio segmenty s pauzami
        final_audio = AudioSegment.empty()
        
        for i, audio in enumerate(audio_segments):
            final_audio += audio
            
            # Přidá pauzu pokud není poslední segment
            if i < len(audio_segments) - 1:
                pause = AudioSegment.silent(duration=pause_duration)
                final_audio += pause
        
        # Uloží finální audio soubor
        output_filename = f"final_output_{uuid.uuid4().hex}.mp3"
        output_path = os.path.join(OUTPUT_FOLDER, output_filename)
        final_audio.export(output_path, format="mp3")
        
        response_data = {
            'success': True,
            'audio_file': output_filename,
            'duration': len(final_audio) / 1000,  # V sekundách
            'segments_count': len(uploaded_files)
        }
        
        # Generuje titulky pokud je to požadováno
        srt_path = None
        if generate_subtitles:
            srt_content = generate_srt_content(audio_segments_info, subtitle_data)
            srt_filename = f"final_output_{uuid.uuid4().hex}.srt"
            srt_path = os.path.join(OUTPUT_FOLDER, srt_filename)
            
            with open(srt_path, 'w', encoding='utf-8') as f:
                f.write(srt_content)
            
            response_data['subtitle_file'] = srt_filename
        
        # Generuje video pokud je to požadováno
        if generate_video:
            video_filename = f"final_output_{uuid.uuid4().hex}.mp4"
            video_path = os.path.join(OUTPUT_FOLDER, video_filename)
            
            # Priorita: 1) Video pozadí, 2) Obrázek pozadí, 3) Waveform
            if video_background_filename:
                # Cesta k video pozadí
                video_background_path = os.path.join(VIDEO_BACKGROUNDS_FOLDER, video_background_filename)
                
                if os.path.exists(video_background_path):
                    print(f"🎥 Používám video pozadí: {video_background_filename}")
                    
                    # Generuje video s video pozadím a titulky
                    video_success, video_message = generate_video_with_video_background(
                        output_path, 
                        video_background_path,
                        srt_path if generate_subtitles else None, 
                        video_path
                    )
                else:
                    video_success = False
                    video_message = f"Video pozadí '{video_background_filename}' nebylo nalezeno"
            elif background_filename:
                # Cesta k obrázku pozadí
                background_path = os.path.join(BACKGROUNDS_FOLDER, background_filename)
                
                if os.path.exists(background_path):
                    print(f"🖼️ Používám obrázek pozadí: {background_filename}")
                    
                    # Generuje video s obrázkem pozadí a titulky
                    video_success, video_message = generate_video_with_background(
                        output_path, 
                        background_path,
                        srt_path if generate_subtitles else None, 
                        video_path
                    )
                else:
                    video_success = False
                    video_message = f"Obrázek pozadí '{background_filename}' nebyl nalezen"
            else:
                print("🌊 Používám waveform pozadí")
                
                # Generuje video s waveform a titulky (původní funkcionalita)
                video_success, video_message = generate_video_with_waveform(
                    output_path, 
                    srt_path if generate_subtitles else None, 
                    video_path
                )
            
            if video_success:
                response_data['video_file'] = video_filename
                response_data['video_message'] = video_message
                if video_background_filename:
                    response_data['video_background_used'] = video_background_filename
                elif background_filename:
                    response_data['background_used'] = background_filename
            else:
                # Pokud video generování selže, nezastaví to celý proces
                response_data['video_error'] = video_message
                print(f"⚠️ Video se nepodařilo vygenerovat: {video_message}")
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({'error': f'Chyba při zpracování: {str(e)}'}), 500

@app.route('/api/generate-voices', methods=['POST'])
def generate_voices():
    """
    Endpoint pro generování hlasů pomocí ElevenLabs API
    """
    try:
        # Získá data z requestu
        print(f"🔍 Request headers: {dict(request.headers)}")
        print(f"🔍 Request content type: {request.content_type}")
        print(f"🔍 Request method: {request.method}")
        
        data = request.get_json()
        print(f"🔍 Received data: {data}")
        print(f"🔍 Data type: {type(data)}")
        
        if not data:
            print("❌ No data received!")
            return jsonify({'error': 'Nebyla poslána žádná data'}), 400
        
        # Povinné parametry
        voice_blocks = data.get('voice_blocks')
        api_key = data.get('api_key')
        
        if not voice_blocks:
            return jsonify({'error': 'Chybí definice hlasových bloků'}), 400
        
        if not api_key:
            return jsonify({'error': 'Chybí ElevenLabs API klíč'}), 400
        
        # Kontrola formátu voice_blocks
        if not isinstance(voice_blocks, dict):
            return jsonify({'error': 'Hlasové bloky musí být ve formátu JSON objektu'}), 400
        
        generated_files = []
        errors = []
        
        # OPRAVA: Zachová pořadí z JSON místo abecedního řazení
        # Generuje každý hlasový blok v pořadí jak byly definovány
        for block_name, block_config in voice_blocks.items():
            try:
                # Validace konfigurace bloku
                text = block_config.get('text')
                # Akceptuje oba formáty: 'voice_id' i 'voice'
                voice_id = block_config.get('voice_id') or block_config.get('voice')
                agent_id = block_config.get('agent_id')
                
                if not text:
                    errors.append(f"Blok '{block_name}': chybí text")
                    continue
                
                # Kontrola, že má buď voice_id nebo agent_id (ale ne oba)
                if voice_id and agent_id:
                    errors.append(f"Blok '{block_name}': nesmí obsahovat současně voice_id a agent_id")
                    continue
                    
                if not voice_id and not agent_id:
                    errors.append(f"Blok '{block_name}': chybí voice_id nebo agent_id")
                    continue
                
                # Vytvoří název souboru
                filename = f"{block_name}.mp3"
                
                # Generuje hlas podle typu (agent_id vs voice_id)
                if agent_id:
                    # Použije ElevenLabs TTS API
                    success, message = generate_voice_with_agent(
                        text=text,
                        agent_id=agent_id,
                        api_key=api_key,
                        filename=filename
                    )
                else:
                    # Použije klasické text-to-speech API
                    success, message = generate_voice_with_elevenlabs(
                        text=text,
                        voice_id=voice_id,
                        api_key=api_key,
                        filename=filename
                    )
                
                if success:
                    generated_files.append({
                        'filename': filename,
                        'block_name': block_name,
                        'message': message,
                        'original_text': text  # Přidá původní text pro lepší debugging
                    })
                else:
                    errors.append(f"Blok '{block_name}': {message}")
                    
            except Exception as e:
                errors.append(f"Blok '{block_name}': {str(e)}")
        
        # Připraví odpověď
        response_data = {
            'success': len(generated_files) > 0,
            'generated_files': generated_files,
            'total_generated': len(generated_files),
            'total_requested': len(voice_blocks)
        }
        
        if errors:
            response_data['errors'] = errors
            response_data['error_count'] = len(errors)
        
        # Určí HTTP status kod
        if len(generated_files) == 0:
            status_code = 400
            response_data['message'] = 'Nepodařilo se vygenerovat žádný hlasový soubor'
        elif len(errors) > 0:
            status_code = 207  # Multi-status
            response_data['message'] = f'Vygenerováno {len(generated_files)}/{len(voice_blocks)} hlasových souborů'
        else:
            status_code = 200
            response_data['message'] = f'Všech {len(generated_files)} hlasových souborů bylo úspěšně vygenerováno'
        
        return jsonify(response_data), status_code
        
    except Exception as e:
        return jsonify({'error': f'Chyba při zpracování: {str(e)}'}), 500

@app.route('/api/files')
def list_files():
    """
    Vrátí seznam dostupných audio souborů ve uploads složce
    """
    try:
        files = []
        if os.path.exists(UPLOAD_FOLDER):
            for filename in os.listdir(UPLOAD_FOLDER):
                if filename.endswith(('.mp3', '.wav', '.m4a')):
                    file_path = os.path.join(UPLOAD_FOLDER, filename)
                    file_size = os.path.getsize(file_path)
                    files.append({
                        'filename': filename,
                        'size': file_size,
                        'modified': os.path.getmtime(file_path)
                    })
        
        # Seřadí podle názvu
        files.sort(key=lambda x: natural_sort_key(x['filename']))
        
        return jsonify({
            'files': files,
            'count': len(files)
        })
    except Exception as e:
        return jsonify({'error': f'Chyba při načítání souborů: {str(e)}'}), 500

@app.route('/api/download/<filename>')
def download_file(filename):
    """
    Stáhne soubor z uploads nebo output složky
    """
    try:
        # Kontrola bezpečnosti - pouze povolené soubory
        if not filename.endswith(('.mp3', '.wav', '.srt', '.mp4')):
            return jsonify({'error': 'Nepovolený typ souboru'}), 400
        
        # Nejdřív zkusí output složku (výsledné soubory)
        output_path = os.path.join(OUTPUT_FOLDER, filename)
        if os.path.exists(output_path):
            response = send_file(output_path, as_attachment=True)
            # Přidá CORS headers
            response.headers.add('Access-Control-Allow-Origin', '*')
            response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
            response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
            return response
        
        # Pak zkusí uploads složku (vstupní soubory)
        upload_path = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(upload_path):
            response = send_file(upload_path, as_attachment=True)
            # Přidá CORS headers
            response.headers.add('Access-Control-Allow-Origin', '*')
            response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
            response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
            return response
        
        return jsonify({'error': 'Soubor nenalezen'}), 404
        
    except Exception as e:
        return jsonify({'error': f'Chyba při stahování: {str(e)}'}), 500

@app.route('/api/upload-background', methods=['POST'])
def upload_background():
    """
    Endpoint pro nahrání obrázků pozadí
    """
    try:
        # Kontrola, zda byl soubor odeslán
        if 'background_file' not in request.files:
            return jsonify({'error': 'Nebyl vybrán žádný soubor'}), 400
        
        file = request.files['background_file']
        
        # Kontrola, zda má soubor název
        if file.filename == '':
            return jsonify({'error': 'Nebyl vybrán žádný soubor'}), 400
        
        # Kontrola typu souboru
        if not allowed_image_file(file.filename):
            return jsonify({'error': 'Nepovolený typ souboru. Povolené: .png, .jpg, .jpeg'}), 400
        
        # Zabezpečení názvu souboru
        filename = secure_filename(file.filename)
        
        # Zkrácení názvu pokud je příliš dlouhý
        name, ext = os.path.splitext(filename)
        # Maximum 50 znaků pro název (bez extension a timestamp)
        if len(name) > 50:
            name = name[:50]
        
        # Přidání timestamp pro jedinečnost
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{name}_{timestamp}{ext}"
        
        # Uložení souboru
        file_path = os.path.join(BACKGROUNDS_FOLDER, unique_filename)
        file.save(file_path)
        
        # Získání velikosti souboru
        file_size = os.path.getsize(file_path)
        
        print(f"🖼️ Nahrán obrázek pozadí: {unique_filename} ({file_size} bytes)")
        
        return jsonify({
            'success': True,
            'filename': unique_filename,
            'original_name': filename,
            'size': file_size,
            'url': f'/api/backgrounds/{unique_filename}',
            'message': 'Obrázek pozadí byl úspěšně nahrán'
        })
        
    except Exception as e:
        print(f"❌ Chyba při nahrávání pozadí: {str(e)}")
        return jsonify({'error': f'Chyba při nahrávání: {str(e)}'}), 500

@app.route('/api/list-backgrounds')
def list_backgrounds():
    """
    Vrátí seznam dostupných obrázků pozadí
    """
    try:
        backgrounds = []
        
        if os.path.exists(BACKGROUNDS_FOLDER):
            for filename in os.listdir(BACKGROUNDS_FOLDER):
                if allowed_image_file(filename):
                    file_path = os.path.join(BACKGROUNDS_FOLDER, filename)
                    file_size = os.path.getsize(file_path)
                    file_mtime = os.path.getmtime(file_path)
                    
                    backgrounds.append({
                        'filename': filename,
                        'size': file_size,
                        'modified': file_mtime,
                        'url': f'/api/backgrounds/{filename}',
                        'thumbnail_url': f'/api/backgrounds/{filename}'  # Prozatím stejné jako plná velikost
                    })
        
        # Seřadí podle data úpravy (nejnovější první)
        backgrounds.sort(key=lambda x: x['modified'], reverse=True)
        
        return jsonify({
            'backgrounds': backgrounds,
            'count': len(backgrounds)
        })
        
    except Exception as e:
        print(f"❌ Chyba při načítání pozadí: {str(e)}")
        return jsonify({'error': f'Chyba při načítání pozadí: {str(e)}'}), 500

@app.route('/api/backgrounds/<filename>')
def serve_background(filename):
    """
    Vrátí obrázek pozadí ze složky backgrounds
    """
    try:
        # Zabezpečení názvu souboru
        filename = secure_filename(filename)
        
        # Kontrola typu souboru
        if not allowed_image_file(filename):
            return jsonify({'error': 'Nepovolený typ souboru'}), 400
        
        file_path = os.path.join(BACKGROUNDS_FOLDER, filename)
        
        if os.path.exists(file_path):
            return send_file(file_path, mimetype='image/jpeg')
        else:
            return jsonify({'error': 'Obrázek nenalezen'}), 404
            
    except Exception as e:
        print(f"❌ Chyba při servování pozadí: {str(e)}")
        return jsonify({'error': f'Chyba při servování obrázku: {str(e)}'}), 500

@app.route('/api/upload-video-background', methods=['POST'])
def upload_video_background():
    """
    Endpoint pro nahrání video pozadí
    """
    try:
        # Kontrola, zda byl soubor odeslán
        if 'video_background_file' not in request.files:
            return jsonify({'error': 'Nebyl vybrán žádný video soubor'}), 400
        
        file = request.files['video_background_file']
        
        # Kontrola, zda má soubor název
        if file.filename == '':
            return jsonify({'error': 'Nebyl vybrán žádný video soubor'}), 400
        
        # Kontrola typu souboru
        if not allowed_video_file(file.filename):
            return jsonify({'error': 'Nepovolený typ souboru. Povolené: .mp4, .mov'}), 400
        
        # Kontrola velikosti souboru (100MB limit)
        file.seek(0, 2)  # Přejde na konec souboru
        file_size = file.tell()
        file.seek(0)  # Vrátí se na začátek
        
        if file_size > 100 * 1024 * 1024:  # 100MB v bytes
            return jsonify({'error': 'Soubor je příliš velký. Maximum je 100MB'}), 400
        
        # Zabezpečení názvu souboru
        filename = secure_filename(file.filename)
        
        # Zkrácení názvu pokud je příliš dlouhý
        name, ext = os.path.splitext(filename)
        # Maximum 50 znaků pro název (bez extension a timestamp)
        if len(name) > 50:
            name = name[:50]
        
        # Přidání timestamp pro jedinečnost
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{name}_{timestamp}{ext}"
        
        # Uložení souboru
        file_path = os.path.join(VIDEO_BACKGROUNDS_FOLDER, unique_filename)
        file.save(file_path)
        
        print(f"🎥 Nahráno video pozadí: {unique_filename} ({file_size} bytes)")
        
        return jsonify({
            'success': True,
            'filename': unique_filename,
            'original_name': filename,
            'size': file_size,
            'url': f'/api/video-backgrounds/{unique_filename}',
            'message': 'Video pozadí bylo úspěšně nahráno'
        })
        
    except Exception as e:
        print(f"❌ Chyba při nahrávání video pozadí: {str(e)}")
        return jsonify({'error': f'Chyba při nahrávání: {str(e)}'}), 500

@app.route('/api/list-video-backgrounds')
def list_video_backgrounds():
    """
    Vrátí seznam dostupných video pozadí
    """
    try:
        video_backgrounds = []
        
        if os.path.exists(VIDEO_BACKGROUNDS_FOLDER):
            for filename in os.listdir(VIDEO_BACKGROUNDS_FOLDER):
                if allowed_video_file(filename):
                    file_path = os.path.join(VIDEO_BACKGROUNDS_FOLDER, filename)
                    file_size = os.path.getsize(file_path)
                    file_mtime = os.path.getmtime(file_path)
                    
                    video_backgrounds.append({
                        'filename': filename,
                        'size': file_size,
                        'modified': file_mtime,
                        'url': f'/api/video-backgrounds/{filename}'
                    })
        
        # Seřadí podle data úpravy (nejnovější první)
        video_backgrounds.sort(key=lambda x: x['modified'], reverse=True)
        
        return jsonify({
            'video_backgrounds': video_backgrounds,
            'count': len(video_backgrounds)
        })
        
    except Exception as e:
        print(f"❌ Chyba při načítání video pozadí: {str(e)}")
        return jsonify({'error': f'Chyba při načítání video pozadí: {str(e)}'}), 500

@app.route('/api/video-backgrounds/<filename>')
def serve_video_background(filename):
    """
    Vrátí video pozadí ze složky video_backgrounds
    """
    try:
        # Zabezpečení názvu souboru
        filename = secure_filename(filename)
        
        # Kontrola typu souboru
        if not allowed_video_file(filename):
            return jsonify({'error': 'Nepovolený typ souboru'}), 400
        
        file_path = os.path.join(VIDEO_BACKGROUNDS_FOLDER, filename)
        
        if os.path.exists(file_path):
            # Nastaví správný MIME type podle přípony
            if filename.lower().endswith('.mp4'):
                mimetype = 'video/mp4'
            elif filename.lower().endswith('.mov'):
                mimetype = 'video/quicktime'
            else:
                mimetype = 'video/mp4'  # fallback
                
            return send_file(file_path, mimetype=mimetype)
        else:
            return jsonify({'error': 'Video nenalezeno'}), 404
            
    except Exception as e:
        print(f"❌ Chyba při servování video pozadí: {str(e)}")
        return jsonify({'error': f'Chyba při servování videa: {str(e)}'}), 500

@app.route('/api/generate-narration', methods=['POST'])
def generate_narration():
    """
    Endpoint pro generování dokumentární narrace pomocí OpenAI GPT-4o
    """
    try:
        # Získá data z POST requestu
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Není posláno žádné JSON data'}), 400
        
        # Kontrola povinných polí
        topic = data.get('topic')
        if not topic:
            return jsonify({'error': 'Pole "topic" je povinné'}), 400
        
        # Volitelné pole pro styl (má výchozí hodnotu)
        style = data.get('style', 'Cinematic, BBC-style, serious tone')
        
        print(f"🎬 Generuji dokumentární naraci...")
        print(f"📝 Téma: {topic}")
        print(f"🎭 Styl: {style}")
        
        # Vytvoří prompt pro OpenAI
        prompt = create_narration_prompt(topic, style)
        
        # Zavolá OpenAI API
        result = call_openai(prompt)
        
        # Kontrola úspěšnosti volání
        if 'error' in result:
            return jsonify({
                'error': f'Chyba při generování narrace: {result["error"]}',
                'details': result.get('raw_content', 'Žádné detaily')
            }), 500
        
        # Získá vygenerovanou naraci
        narration_data = result['data']
        
        # Vytvoří slug z tématu pro složku
        slug = re.sub(r'[^a-zA-Z0-9\s-]', '', topic.lower())
        slug = re.sub(r'\s+', '-', slug.strip())
        slug = slug[:50]  # Maximálně 50 znaků
        
        # Vytvoří složku pro projekt
        project_folder = os.path.join(PROJECTS_FOLDER, slug)
        os.makedirs(project_folder, exist_ok=True)
        
        # Uloží naraci do JSON souboru
        narration_file_path = os.path.join(project_folder, 'narration.json')
        with open(narration_file_path, 'w', encoding='utf-8') as f:
            json.dump(narration_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Narrace úspěšně vygenerována a uložena")
        print(f"📁 Projekt uložen do: {project_folder}")
        print(f"📊 Počet narativních bloků: {len(narration_data)}")
        
        # Vytvoří metadata soubor
        metadata = {
            'topic': topic,
            'style': style,
            'generated_at': datetime.now().isoformat(),
            'slug': slug,
            'blocks_count': len(narration_data),
            'file_path': narration_file_path
        }
        
        metadata_file_path = os.path.join(project_folder, 'metadata.json')
        with open(metadata_file_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        return jsonify({
            'success': True,
            'message': 'Dokumentární narrace byla úspěšně vygenerována',
            'data': {
                'narration': narration_data,
                'metadata': metadata,
                'project_folder': project_folder,
                'narration_file': narration_file_path
            }
        })
        
    except Exception as e:
        error_msg = f"Neočekávaná chyba při generování narrace: {str(e)}"
        print(f"❌ {error_msg}")
        return jsonify({'error': error_msg}), 500

@app.route('/api/health')
def health_check():
    """
    Jednoduchý health check endpoint
    """
    return jsonify({'status': 'Backend funguje správně!'})

if __name__ == '__main__':
    print("🎵 AI Voice Block Combiner Backend")
    print("📂 Upload folder:", UPLOAD_FOLDER)
    print("📁 Output folder:", OUTPUT_FOLDER)
    print("🌐 Server běží na: http://localhost:5000")
    # Spuštění bez vestavěného reloaderu, aby server nespadl při běhu na pozadí
    # Používáme debug=False, protože printujeme vlastní ladicí zprávy a reloader by v pozadí způsoboval chyby termios
    app.run(debug=False, host='0.0.0.0', port=5000, use_reloader=False) 