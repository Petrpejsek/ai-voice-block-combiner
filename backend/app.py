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
        
        # 🔧 NORMALIZACE ČÍSLOVÁNÍ - zajistí konzistentní formát 01, 02, 03
        voice_blocks = normalize_block_numbering(voice_blocks)
        
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

@app.route('/api/generated-projects')
def list_generated_projects():
    """
    Vrátí seznam vygenerovaných projektů (zatím prázdný - projekty se ukládají pouze v frontend)
    """
    try:
        # Pro nyní vracíme prázdný seznam, protože projekty se ukládají v frontend localStorage
        # V budoucnu by se mohly ukládat na backend
        return jsonify({
            'projects': [],
            'count': 0,
            'message': 'Projekty se ukládají lokálně v prohlížeči'
        })
    except Exception as e:
        print(f"❌ Chyba při načítání projektů: {str(e)}")
        return jsonify({'error': f'Chyba při načítání projektů: {str(e)}'}), 500

@app.route('/api/openai-assistant', methods=['POST'])
def openai_assistant():
    """
    Obecný OpenAI asistent endpoint pro různé typy dotazů
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Chybí JSON data'}), 400
        
        assistant_type = data.get('assistant_type', 'general')
        prompt = data.get('prompt', '')
        
        if not prompt.strip():
            return jsonify({'error': 'Prompt nemůže být prázdný'}), 400
        
        print(f"🤖 OpenAI Asistent požadavek - typ: {assistant_type}")
        print(f"📝 Prompt: {prompt[:100]}...")
        
        # Definuje systémové prompty pro různé typy asistentů
        system_prompts = {
            'general': "Jste užitečný AI asistent. Odpovídejte jasně a informativně na dotazy uživatele v českém jazyce.",
            'creative': "Jste kreativní asistent specializovaný na psaní, nápady a uměleckou tvorbu. Buďte kreativní a inspirativní. Odpovídejte v češtině.",
            'technical': "Jste technický asistent specializovaný na programování, technologie a řešení problémů. Poskytujte praktické a přesné rady. Odpovídejte v češtině.",
            'podcast': "Jste asistent specializovaný na tvorbu podcastů, dialogů a audio obsahu. Pomáháte s plánováním, strukturou a obsahem. Odpovídejte v češtině.",
            'research': "Jste výzkumný asistent specializovaný na analýzu dat, výzkum a faktické informace. Buďte přesní a založení na datech. Odpovídejte v češtině."
        }
        
        system_prompt = system_prompts.get(assistant_type, system_prompts['general'])
        
        # Volá obecnější verzi OpenAI API (bez JSON formátu)
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            return jsonify({'error': 'OpenAI API klíč není nastaven'}), 500
        
        # Přímé volání OpenAI API bez JSON omezení
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        data_payload = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 2000
        }
        
        response = requests.post(url, json=data_payload, headers=headers, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            assistant_response = result['choices'][0]['message']['content']
            
            print(f"✅ OpenAI asistent úspěšně odpověděl")
            return jsonify({
                'success': True,
                'response': assistant_response,
                'assistant_type': assistant_type
            })
        else:
            error_msg = f"OpenAI API chyba: {response.status_code} - {response.text}"
            print(f"❌ {error_msg}")
            return jsonify({'error': error_msg}), 500
            
    except requests.exceptions.Timeout:
        error_msg = "Časový limit OpenAI API volání byl překročen"
        print(f"❌ {error_msg}")
        return jsonify({'error': error_msg}), 408
    except Exception as e:
        error_msg = f"Neočekávaná chyba: {str(e)}"
        print(f"❌ {error_msg}")
        return jsonify({'error': error_msg}), 500

@app.route('/api/health')
def health_check():
    """
    Jednoduchý health check endpoint
    """
    return jsonify({'status': 'Backend funguje správně!'})

@app.route('/api/generate-image', methods=['POST'])
def generate_image():
    """
    Endpoint pro generování obrázků pomocí DALL-E 3
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Chybí JSON data'}), 400
        
        # Kontrola povinných polí
        prompt = data.get('prompt')
        api_key = data.get('api_key')
        
        if not prompt:
            return jsonify({'error': 'Pole "prompt" je povinné'}), 400
        
        if not api_key:
            return jsonify({'error': 'OpenAI API klíč je povinný'}), 400
        
        # Volitelné parametry
        size = data.get('size', '1024x1024')  # 1024x1024, 1792x1024, nebo 1024x1792
        quality = data.get('quality', 'standard')  # standard nebo hd
        
        print(f"🎨 Generuji obrázek...")
        print(f"📝 Prompt: {prompt}")
        print(f"📏 Velikost: {size}")
        print(f"✨ Kvalita: {quality}")
        
        # DALL-E 3 API call
        url = "https://api.openai.com/v1/images/generations"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        payload = {
            "model": "dall-e-3",
            "prompt": prompt,
            "n": 1,
            "size": size,
            "quality": quality,
            "response_format": "url"
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            image_url = result['data'][0]['url']
            revised_prompt = result['data'][0].get('revised_prompt', prompt)
            
            # Stáhne obrázek a uloží ho lokálně
            image_response = requests.get(image_url, timeout=30)
            if image_response.status_code == 200:
                # Vytvoří název souboru
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"dalle_image_{timestamp}.png"
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                
                # Uloží obrázek
                with open(filepath, 'wb') as f:
                    f.write(image_response.content)
                
                print(f"✅ Obrázek úspěšně vygenerován: {filename}")
                
                return jsonify({
                    'success': True,
                    'message': 'Obrázek úspěšně vygenerován',
                    'data': {
                        'filename': filename,
                        'original_prompt': prompt,
                        'revised_prompt': revised_prompt,
                        'size': size,
                        'quality': quality,
                        'url': image_url,
                        'local_path': filepath
                    }
                })
            else:
                return jsonify({'error': 'Chyba při stahování vygenerovaného obrázku'}), 500
        else:
            error_msg = f"DALL-E API chyba: {response.status_code} - {response.text}"
            print(f"❌ {error_msg}")
            return jsonify({'error': error_msg}), 500
            
    except requests.exceptions.Timeout:
        error_msg = "Časový limit DALL-E API volání byl překročen"
        print(f"❌ {error_msg}")
        return jsonify({'error': error_msg}), 408
    except Exception as e:
        error_msg = f"Neočekávaná chyba při generování obrázku: {str(e)}"
        print(f"❌ {error_msg}")
        return jsonify({'error': error_msg}), 500

@app.route('/api/openai-assistant-call', methods=['POST'])
def openai_assistant_call():
    """
    Endpoint pro volání OpenAI Assistant API
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Chybí JSON data'}), 400
        
        # Kontrola povinných polí
        assistant_id = data.get('assistant_id')
        prompt = data.get('prompt')
        api_key = data.get('api_key')
        
        if not assistant_id:
            return jsonify({'error': 'Assistant ID je povinné'}), 400
        
        if not prompt:
            return jsonify({'error': 'Prompt je povinný'}), 400
        
        if not api_key:
            return jsonify({'error': 'OpenAI API klíč je povinný'}), 400
        
        # Validace formátu Assistant ID
        if not assistant_id.startswith('asst_'):
            return jsonify({'error': 'Assistant ID musí začínat "asst_"'}), 400
        
        print(f"🤖 Volám OpenAI Assistant...")
        print(f"📝 Assistant ID: {assistant_id}")
        print(f"💬 Prompt: {prompt[:100]}...")
        
        # OpenAI Assistants API volání
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "OpenAI-Beta": "assistants=v2"
        }
        
        # Step 1: Vytvoř thread
        thread_response = requests.post(
            "https://api.openai.com/v1/threads",
            headers=headers,
            json={},
            timeout=30
        )
        
        if thread_response.status_code != 200:
            return jsonify({'error': f'Chyba při vytváření thread: {thread_response.text}'}), 500
        
        thread_id = thread_response.json()['id']
        
        # Step 2: Přidej zprávu do thread
        message_response = requests.post(
            f"https://api.openai.com/v1/threads/{thread_id}/messages",
            headers=headers,
            json={
                "role": "user",
                "content": prompt
            },
            timeout=30
        )
        
        if message_response.status_code != 200:
            return jsonify({'error': f'Chyba při přidávání zprávy: {message_response.text}'}), 500
        
        # Step 3: Spusť assistant
        run_response = requests.post(
            f"https://api.openai.com/v1/threads/{thread_id}/runs",
            headers=headers,
            json={
                "assistant_id": assistant_id
            },
            timeout=30
        )
        
        if run_response.status_code != 200:
            return jsonify({'error': f'Chyba při spouštění assistant: {run_response.text}'}), 500
        
        run_id = run_response.json()['id']
        
        # Step 4: Čekej na dokončení (polling)
        max_attempts = 60  # 60 sekund max
        for attempt in range(max_attempts):
            status_response = requests.get(
                f"https://api.openai.com/v1/threads/{thread_id}/runs/{run_id}",
                headers=headers,
                timeout=10
            )
            
            if status_response.status_code != 200:
                return jsonify({'error': f'Chyba při kontrole stavu: {status_response.text}'}), 500
            
            status = status_response.json()['status']
            
            if status == 'completed':
                break
            elif status in ['failed', 'cancelled', 'expired']:
                return jsonify({'error': f'Assistant run selhál se stavem: {status}'}), 500
            
            # Čekej 1 sekundu před dalším pokusem
            import time
            time.sleep(1)
        else:
            return jsonify({'error': 'Časový limit pro dokončení assistant běhu překročen'}), 408
        
        # Step 5: Získej odpověď
        messages_response = requests.get(
            f"https://api.openai.com/v1/threads/{thread_id}/messages",
            headers=headers,
            timeout=30
        )
        
        if messages_response.status_code != 200:
            return jsonify({'error': f'Chyba při získávání zpráv: {messages_response.text}'}), 500
        
        messages = messages_response.json()['data']
        
        # Najdi posledníu odpověď od assistanta
        assistant_message = None
        for message in messages:
            if message['role'] == 'assistant' and message['content']:
                assistant_message = message['content'][0]['text']['value']
                break
        
        if not assistant_message:
            return jsonify({'error': 'Nepodařilo se získat odpověď od assistanta'}), 500
        
        print(f"✅ OpenAI Assistant úspěšně odpověděl")
        
        return jsonify({
            'success': True,
            'message': 'OpenAI Assistant úspěšně odpověděl',
            'data': {
                'assistant_id': assistant_id,
                'thread_id': thread_id,
                'run_id': run_id,
                'response': assistant_message,
                'original_prompt': prompt
            }
        })
        
    except requests.exceptions.Timeout:
        error_msg = "Časový limit OpenAI Assistant API volání byl překročen"
        print(f"❌ {error_msg}")
        return jsonify({'error': error_msg}), 408
    except Exception as e:
        error_msg = f"Neočekávaná chyba při volání OpenAI Assistant: {str(e)}"
        print(f"❌ {error_msg}")
        return jsonify({'error': error_msg}), 500

@app.route('/api/generate-video-structure', methods=['POST'])
def generate_video_structure():
    """
    SPRÁVNÁ IMPLEMENTACE UŽIVATELOVA ZADÁNÍ:
    - JEDEN segment = 1800 slov (ne více segmentů)
    - Backend pošle 3 zprávy: 600 + 600 + 600 slov
    - Frontend dostane JEDEN segment k zpracování
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Chybí JSON data'}), 400
        
        # Pouze základní data
        topic = data.get('topic', 'electricity and innovation')
        target_minutes = data.get('target_minutes', 12)
        detail_assistant_id = data.get('detail_assistant_id')
        api_key = data.get('api_key')
        
        if not api_key:
            return jsonify({'error': 'OpenAI API klíč je povinný'}), 400
            
        if not detail_assistant_id:
            return jsonify({'error': 'Detail Assistant ID je povinné'}), 400
        
        # DYNAMICKÝ POČET SLOV z frontendu
        target_words = data.get('target_words', target_minutes * 150)  # 150 slov/minutu jako fallback
        TARGET_TOTAL = target_words
        
        print(f"🎯 SPRÁVNÁ IMPLEMENTACE ZADÁNÍ")
        print(f"📝 Topic: {topic}")
        print(f"⏱️ Cíl: {target_minutes} minut = {TARGET_TOTAL} slov")
        print(f"📊 Segmentů: 1 (JEDEN segment s {TARGET_TOTAL} slovy)")
        print(f"🤖 Detail Assistant: {detail_assistant_id}")
        
        # POUZE JEDEN SEGMENT - backend ho rozdělí na části podle počtu slov
        segments = [
            {
                'id': 'main_segment',
                'target_words': TARGET_TOTAL,
                'main_topic': topic,
                'title': f'Tesla vs Socrates: {topic}',
                'duration_minutes': target_minutes
            }
        ]
        
        return jsonify({
            'success': True,
            'message': f'Struktura připravena - 1 segment s {TARGET_TOTAL} slovy',
            'data': {
                'detail_assistant_id': detail_assistant_id,
                'segments': segments,
                'video_context': {
                    'main_topic': topic,
                    'target_minutes': target_minutes,
                    'target_words': TARGET_TOTAL,
                    'total_segments': 1
                }
            }
        })
        
    except Exception as e:
        error_msg = f"Chyba při přípravě struktury: {str(e)}"
        print(f"❌ {error_msg}")
        return jsonify({'error': error_msg}), 500

@app.route('/api/generate-segment-content', methods=['POST'])
def generate_segment_content():
    """
    UNIVERZÁLNÍ GENEROVÁNÍ OBSAHU:
    - PODCAST: Tesla vs Socrates dialog (2 hlasy)
    - DOCUMENT: Continuous narration (1 hlas)
    Kategorie se určuje z assistant_category v požadavku
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Chybí JSON data'}), 400
        
        # Kontrola povinných polí
        detail_assistant_id = data.get('detail_assistant_id')
        segment_info = data.get('segment_info')
        api_key = data.get('api_key')
        assistant_category = data.get('assistant_category', 'podcast')  # default: podcast
        narrator_voice_id = data.get('narrator_voice_id', 'fb6f5b20hmCY0fO9Gr8v')  # default voice
        
        if not segment_info or not api_key:
            return jsonify({'error': 'Chybí povinná data'}), 400
        
        segment_id = segment_info.get('id', 'unknown')
        topic = segment_info.get('main_topic', 'electricity and innovation')
        target_words = segment_info.get('target_words', 1800)  # Získej počet slov ze segment_info
        
        print(f"🎯 UNIVERZÁLNÍ GENEROVÁNÍ")
        print(f"📝 Topic: {topic}")
        print(f"🎭 Kategorie: {assistant_category.upper()}")
        if assistant_category == 'document':
            print(f"🎤 Narrator Voice ID: {narrator_voice_id}")
        print(f"⏱️ Cíl: JEDEN segment = {target_words} slov")
        
        # DYNAMICKÉ ROZDĚLENÍ NA ČÁSTI
        WORDS_PER_PART = 600  # Konstantní velikost části
        PARTS_COUNT = max(1, (target_words + WORDS_PER_PART - 1) // WORDS_PER_PART)  # Ceiling division
        TARGET_TOTAL = target_words
        
        print(f"📊 Metoda: {PARTS_COUNT} částí po ~{WORDS_PER_PART} slovech = {TARGET_TOTAL} slov")
        
        # OpenAI API setup
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "OpenAI-Beta": "assistants=v2"
        }
        
        # ŘEŠENÍ PROBLÉMU: Vytvoř nový Detail Assistant pro každé zadání
        # Tím se zajistí, že si nepamatuje předchozí konverzace
        print(f"🆕 Vytvářím nový Detail Assistant pro čerstvý obsah...")
        
        # Vytvoř nový Detail Assistant
        assistant_data = {
            "model": "gpt-4o",
            "name": f"Detail Assistant - {assistant_category.title()}",
            "instructions": f"""You are a Detail Assistant specialized in generating {'podcast dialogues' if assistant_category == 'podcast' else 'document narrations'}.

Your task is to generate content in JSON format with precise word counts.

For PODCAST mode:
- Generate Tesla vs Socrates philosophical dialogues
- Use Tesla_01, Socrates_01, Tesla_02, Socrates_02, etc.
- Tesla voice_id: "fb6f5b20hmCY0fO9Gr8v"
- Socrates voice_id: "Ezn5SsWzN9rYHvvWrFnm"

For DOCUMENT mode:
- Generate continuous narration
- Use Narrator_01, Narrator_02, Narrator_03, etc.
- Use provided narrator voice_id

Always:
- Count words precisely
- Generate exactly the requested word count
- Output only valid JSON
- Each text block should be 35-45 words
- Maintain engaging, high-quality content""",
            "tools": []
        }
        
        create_assistant_resp = requests.post(
            "https://api.openai.com/v1/assistants",
            headers=headers,
            json=assistant_data,
            timeout=30
        )
        
        if create_assistant_resp.status_code != 200:
            return jsonify({'error': f'Chyba při vytváření Detail Assistant: {create_assistant_resp.text}'}), 500
        
        new_detail_assistant_id = create_assistant_resp.json()['id']
        print(f"✅ Vytvořen nový Detail Assistant: {new_detail_assistant_id}")
        
        # Použij nový Assistant ID místo starého
        detail_assistant_id = new_detail_assistant_id
        
        # Helper funkce pro komunikaci s assistantem
        def send_to_assistant(thread_id: str, message: str, assistant_id: str):
            # Přidej zprávu
            requests.post(
                f"https://api.openai.com/v1/threads/{thread_id}/messages",
                headers=headers,
                json={"role": "user", "content": message},
                timeout=30
            )
            # Spusť run
            run_resp = requests.post(
                f"https://api.openai.com/v1/threads/{thread_id}/runs",
                headers=headers,
                json={"assistant_id": assistant_id},
                timeout=30
            )
            run_id = run_resp.json()['id']
            
            # Čekej na dokončení
            for _ in range(180):
                status_resp = requests.get(
                    f"https://api.openai.com/v1/threads/{thread_id}/runs/{run_id}",
                    headers=headers,
                    timeout=10
                )
                status = status_resp.json()['status']
                if status == 'completed':
                    break
                if status in ['failed', 'cancelled', 'expired']:
                    raise RuntimeError(f"Assistant run failed: {status}")
                import time; time.sleep(1)
            
            # Získej odpověď
            msg_resp = requests.get(
                f"https://api.openai.com/v1/threads/{thread_id}/messages",
                headers=headers,
                timeout=30
            )
            for m in msg_resp.json()['data']:
                if m['role'] == 'assistant' and m['content']:
                    return m['content'][0]['text']['value']
            raise RuntimeError("No assistant response found")
        
        # JSON parsing
        import json, re
        def clean_json(text: str):
            text = text.strip()
            if text.startswith('```json'):
                text = re.sub(r'^```json', '', text).strip()
            if text.endswith('```'):
                text = re.sub(r'```$', '', text).strip()
            elif text.startswith('```'):
                text = text.replace('```', '').strip()
            return text
        
        # DŮLEŽITÉ: Vytvoř NOVÝ thread pro každé zadání (aby se nepamatoval předchozí obsah)
        thread_resp = requests.post("https://api.openai.com/v1/threads", headers=headers, json={}, timeout=30)
        thread_id = thread_resp.json()['id']
        print(f"🆕 Vytvořen nový thread: {thread_id[:8]}... (pro čerstvý obsah)")
        
        # IMPLEMENTACE PRO OBA TYPY
        combined_json = {}
        total_words = 0
        
        print(f"📊 Plán: {PARTS_COUNT} částí po {WORDS_PER_PART} slovech = {TARGET_TOTAL} slov")
        
        # POSTUPNÉ GENEROVÁNÍ S DYNAMICKÝM POČTEM ČÁSTÍ
        for part_num in range(1, PARTS_COUNT + 1):
            print(f"🔄 Část {part_num}/{PARTS_COUNT}: {WORDS_PER_PART} slov")
            
            if part_num == 1:
                # PRVNÍ PROMPT - podle kategorie
                if assistant_category == 'podcast':
                    # PODCAST: Tesla vs Socrates dialog
                    import random
                    import time
                    unique_seed = f"{topic}_{int(time.time())}_{random.randint(1000, 9999)}"
                    
                    prompt = f"""Generate Tesla vs Socrates dialogue about: {topic}

UNIQUE REQUEST ID: {unique_seed}

CRITICAL REQUIREMENT: Generate exactly {WORDS_PER_PART} words.

Format: JSON with Tesla_01, Socrates_01, Tesla_02, Socrates_02, etc.
Each dialogue block should be 35-45 words.

Create engaging philosophical dialogue between Tesla and Socrates about {topic}.
Start numbering from 01 (Tesla_01, Socrates_01, Tesla_02, Socrates_02, etc.).

IMPORTANT: This is a FRESH conversation. Do not repeat any previous content.
Explore different aspects of {topic} - be creative and original.

You need approximately {WORDS_PER_PART // 40} dialogue blocks to reach {WORDS_PER_PART} words.

Output ONLY valid JSON:
{{
  "Tesla_01": {{"voice_id": "fb6f5b20hmCY0fO9Gr8v", "text": "..."}},
  "Socrates_01": {{"voice_id": "Ezn5SsWzN9rYHvvWrFnm", "text": "..."}},
  "Tesla_02": {{"voice_id": "fb6f5b20hmCY0fO9Gr8v", "text": "..."}},
  "Socrates_02": {{"voice_id": "Ezn5SsWzN9rYHvvWrFnm", "text": "..."}},
  ...
}}

IMPORTANT: Count your words carefully and generate exactly {WORDS_PER_PART} words total."""
                
                else:  # document
                    # DOCUMENT: Continuous narration
                    import random
                    import time
                    unique_seed = f"{topic}_{int(time.time())}_{random.randint(1000, 9999)}"
                    
                    prompt = f"""Generate continuous narration about: {topic}

UNIQUE REQUEST ID: {unique_seed}

CRITICAL REQUIREMENT: Generate exactly {WORDS_PER_PART} words.

Format: JSON with Narrator_01, Narrator_02, Narrator_03, etc.
Each narration block should be 35-45 words.

Create engaging, informative narration about {topic}.
Start numbering from 01 (Narrator_01, Narrator_02, Narrator_03, etc.).

IMPORTANT: This is a FRESH narration. Do not repeat any previous content.
Explore different aspects of {topic} - be creative and original.

You need approximately {WORDS_PER_PART // 40} narration blocks to reach {WORDS_PER_PART} words.

Output ONLY valid JSON:
{{
  "Narrator_01": {{"voice_id": "{narrator_voice_id}", "text": "..."}},
  "Narrator_02": {{"voice_id": "{narrator_voice_id}", "text": "..."}},
  "Narrator_03": {{"voice_id": "{narrator_voice_id}", "text": "..."}},
  "Narrator_04": {{"voice_id": "{narrator_voice_id}", "text": "..."}},
  ...
}}

IMPORTANT: Count your words carefully and generate exactly {WORDS_PER_PART} words total."""
                
                print(f"📤 Posílám PRVNÍ PROMPT: {WORDS_PER_PART} slov ({assistant_category})")
                
            else:
                # ZJISTI POSLEDNÍ ČÍSLO Z PŘEDCHOZÍCH ČÁSTÍ - OPRAVENÁ LOGIKA
                if assistant_category == 'podcast':
                    # PODCAST: Tesla a Socrates
                    last_tesla_num = 0
                    last_socrates_num = 0
                    
                    # Projdi všechny klíče a najdi nejvyšší čísla
                    for key in combined_json.keys():
                        if key.startswith('Tesla_'):
                            try:
                                # Ošetři různé formáty číslování (01, 1, atd.)
                                num_str = key.split('_')[1]
                                num = int(num_str)
                                last_tesla_num = max(last_tesla_num, num)
                            except (IndexError, ValueError):
                                continue
                        elif key.startswith('Socrates_'):
                            try:
                                num_str = key.split('_')[1]
                                num = int(num_str)
                                last_socrates_num = max(last_socrates_num, num)
                            except (IndexError, ValueError):
                                continue
                    
                    # KLÍČOVÁ OPRAVA: Pokračuj od posledního čísla + 1
                    next_tesla_num = last_tesla_num + 1
                    next_socrates_num = last_socrates_num + 1
                    
                    # CONTINUE ZPRÁVY - podcast
                    prompt = f"""Continue with another {WORDS_PER_PART} words.

Continue the Tesla vs Socrates dialogue about {topic}.

CRITICAL NUMBERING: Continue from where you left off:
- Next Tesla dialogue should be Tesla_{next_tesla_num:02d}
- Next Socrates dialogue should be Socrates_{next_socrates_num:02d}
- Continue alternating Tesla and Socrates from these numbers

Keep the philosophical discussion flowing naturally.

CRITICAL REQUIREMENT: Generate exactly {WORDS_PER_PART} words.
You need approximately {WORDS_PER_PART // 40} more dialogue blocks.

Output ONLY valid JSON with continued numbering.
Each dialogue block should be 35-45 words.

Example start:
{{
  "Tesla_{next_tesla_num:02d}": {{"voice_id": "fb6f5b20hmCY0fO9Gr8v", "text": "..."}},
  "Socrates_{next_socrates_num:02d}": {{"voice_id": "Ezn5SsWzN9rYHvvWrFnm", "text": "..."}},
  ...
}}

IMPORTANT: Count your words carefully and generate exactly {WORDS_PER_PART} words total."""
                    
                    print(f"📤 Posílám CONTINUE ZPRÁVU #{part_num-1}: dalších {WORDS_PER_PART} slov (podcast)")
                    print(f"🔢 Poslední čísla: Tesla_{last_tesla_num:02d}, Socrates_{last_socrates_num:02d}")
                    print(f"🔢 Pokračování od Tesla_{next_tesla_num:02d}, Socrates_{next_socrates_num:02d}")
                    
                else:  # document
                    # DOCUMENT: Narrator - OPRAVENÁ LOGIKA
                    last_narrator_num = 0
                    
                    # Projdi všechny klíče a najdi nejvyšší číslo
                    for key in combined_json.keys():
                        if key.startswith('Narrator_'):
                            try:
                                # Ošetři různé formáty číslování (01, 1, atd.)
                                num_str = key.split('_')[1]
                                num = int(num_str)
                                last_narrator_num = max(last_narrator_num, num)
                            except (IndexError, ValueError):
                                continue
                    
                    # KLÍČOVÁ OPRAVA: Pokračuj od posledního čísla + 1
                    next_narrator_num = last_narrator_num + 1
                    
                    # CONTINUE ZPRÁVY - document
                    prompt = f"""Continue with another {WORDS_PER_PART} words.

Continue the narration about {topic}.

CRITICAL NUMBERING: Continue from where you left off:
- Next narration block should be Narrator_{next_narrator_num:02d}
- Continue sequential numbering from this number

Keep the narration flowing naturally and informatively.

CRITICAL REQUIREMENT: Generate exactly {WORDS_PER_PART} words.
You need approximately {WORDS_PER_PART // 40} more narration blocks.

Output ONLY valid JSON with continued numbering.
Each narration block should be 35-45 words.

Example start:
{{
  "Narrator_{next_narrator_num:02d}": {{"voice_id": "{narrator_voice_id}", "text": "..."}},
  "Narrator_{next_narrator_num+1:02d}": {{"voice_id": "{narrator_voice_id}", "text": "..."}},
  ...
}}

IMPORTANT: Count your words carefully and generate exactly {WORDS_PER_PART} words total."""
                    
                    print(f"📤 Posílám CONTINUE ZPRÁVU #{part_num-1}: dalších {WORDS_PER_PART} slov (document)")
                    print(f"🔢 Poslední číslo: Narrator_{last_narrator_num:02d}")
                    print(f"🔢 Pokračování od Narrator_{next_narrator_num:02d}")
            
            # Pošli prompt assistantovi (použij NOVÝ Detail Assistant ID)
            response = send_to_assistant(thread_id, prompt, detail_assistant_id)
            
            try:
                # Parsuj JSON odpověď
                part_json = json.loads(clean_json(response))
                
                # 🔧 NORMALIZACE ČÍSLOVÁNÍ - zajistí konzistentní formát 01, 02, 03
                part_json = normalize_block_numbering(part_json)
                
                # Spočítej slova v této části
                part_words = 0
                for block_data in part_json.values():
                    if isinstance(block_data, dict) and 'text' in block_data:
                        part_words += len(block_data['text'].split())
                
                print(f"✅ Část {part_num}: {part_words} slov, {len(part_json)} bloků")
                
                # SCRIPT POUZE SPOJUJE (bez přečíslování)
                combined_json.update(part_json)
                total_words += part_words
                
            except Exception as e:
                print(f"❌ Chyba při parsování části {part_num}: {e}")
                if part_num == 1:
                    raise e
                else:
                    break
        
        print(f"🎉 HOTOVO: {total_words} slov z cílových {TARGET_TOTAL} ({total_words/TARGET_TOTAL*100:.1f}%)")
        print(f"📋 Celkem bloků: {len(combined_json)}")
        print(f"📋 Ukázka bloků: {list(combined_json.keys())[:5]}...")
        
        # CLEANUP: Smaž vytvořený Detail Assistant
        try:
            delete_resp = requests.delete(
                f"https://api.openai.com/v1/assistants/{detail_assistant_id}",
                headers=headers,
                timeout=10
            )
            if delete_resp.status_code == 200:
                print(f"🗑️ Detail Assistant smazán: {detail_assistant_id}")
            else:
                print(f"⚠️ Nepodařilo se smazat Detail Assistant: {delete_resp.status_code}")
        except Exception as e:
            print(f"⚠️ Chyba při mazání Detail Assistant: {e}")
        
        return jsonify({
            'success': True,
            'message': f'Segment vygenerován postupně: {total_words} slov ({assistant_category})',
            'data': {
                'detail_assistant_id': detail_assistant_id,
                'thread_id': thread_id,
                'segment_content': combined_json,
                'word_count': total_words,
                'block_count': len(combined_json),
                'target_words': TARGET_TOTAL,
                'completion_percentage': round(total_words/TARGET_TOTAL*100, 1),
                'category': assistant_category
            }
        })
        
    except Exception as e:
        print(f"❌ Chyba při generování segmentu: {e}")
        
        # CLEANUP: Smaž vytvořený Detail Assistant i při chybě
        try:
            if 'detail_assistant_id' in locals():
                delete_resp = requests.delete(
                    f"https://api.openai.com/v1/assistants/{detail_assistant_id}",
                    headers=headers,
                    timeout=10
                )
                if delete_resp.status_code == 200:
                    print(f"🗑️ Detail Assistant smazán po chybě: {detail_assistant_id}")
        except Exception as cleanup_error:
            print(f"⚠️ Chyba při mazání Detail Assistant po chybě: {cleanup_error}")
        
        return jsonify({'error': str(e)}), 500

@app.route('/api/test-api-connections', methods=['POST'])
def test_api_connections():
    """
    Endpoint pro testování API připojení
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Chybí JSON data'}), 400
        
        results = {}
        
        # Test OpenAI API
        openai_key = data.get('openai_api_key', '')
        if openai_key:
            try:
                url = "https://api.openai.com/v1/models"
                headers = {"Authorization": f"Bearer {openai_key}"}
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    results['openai'] = {'status': 'success', 'message': 'OpenAI API připojení úspěšné'}
                else:
                    results['openai'] = {'status': 'error', 'message': f'OpenAI API chyba: {response.status_code}'}
            except Exception as e:
                results['openai'] = {'status': 'error', 'message': f'OpenAI API chyba: {str(e)}'}
        else:
            results['openai'] = {'status': 'skipped', 'message': 'OpenAI API klíč není nastaven'}
        
        # Test ElevenLabs API
        elevenlabs_key = data.get('elevenlabs_api_key', '')
        if elevenlabs_key:
            try:
                url = "https://api.elevenlabs.io/v1/voices"
                headers = {"xi-api-key": elevenlabs_key}
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    results['elevenlabs'] = {'status': 'success', 'message': 'ElevenLabs API připojení úspěšné'}
                else:
                    results['elevenlabs'] = {'status': 'error', 'message': f'ElevenLabs API chyba: {response.status_code}'}
            except Exception as e:
                results['elevenlabs'] = {'status': 'error', 'message': f'ElevenLabs API chyba: {str(e)}'}
        else:
            results['elevenlabs'] = {'status': 'skipped', 'message': 'ElevenLabs API klíč není nastaven'}
        
        return jsonify({
            'success': True,
            'message': 'API testy dokončeny',
            'results': results
        })
        
    except Exception as e:
        return jsonify({'error': f'Chyba při testování API: {str(e)}'}), 500

# Lokální seznam skrytých asistentů (v reálné aplikaci by to bylo v databázi)
hidden_assistants = set()

@app.route('/api/list-assistants', methods=['POST'])
def list_assistants():
    """
    Zobrazí seznam asistentů (bez skrytých)
    """
    try:
        data = request.get_json()
        
        if not data or 'openai_api_key' not in data:
            return jsonify({'error': 'Chybí OpenAI API klíč'}), 400
        
        api_key = data['openai_api_key']
        
        if not api_key:
            return jsonify({'error': 'OpenAI API klíč je povinný'}), 400
        
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'OpenAI-Beta': 'assistants=v2'
        }
        
        # Získej všechny asistenty z OpenAI
        response = requests.get('https://api.openai.com/v1/assistants', headers=headers)
        
        if response.status_code != 200:
            return jsonify({'error': f'OpenAI API chyba: {response.text}'}), 400
        
        all_assistants = response.json().get('data', [])
        
        # Filtruj skryté asistenty
        visible_assistants = [
            assistant for assistant in all_assistants 
            if assistant['id'] not in hidden_assistants
        ]
        
        return jsonify({
            'assistants': visible_assistants,
            'total': len(visible_assistants),
            'hidden_count': len(hidden_assistants)
        })
        
    except Exception as e:
        return jsonify({'error': f'Chyba při načítání asistentů: {str(e)}'}), 500

@app.route('/api/hide-assistant', methods=['POST'])
def hide_assistant():
    """
    Skryje asistenta z lokálního seznamu (nemaže z OpenAI)
    """
    try:
        data = request.get_json()
        
        if not data or 'assistant_id' not in data:
            return jsonify({'error': 'Chybí ID asistenta'}), 400
        
        assistant_id = data['assistant_id']
        hidden_assistants.add(assistant_id)
        
        return jsonify({
            'success': True, 
            'message': f'Asistent {assistant_id} byl skryt z seznamu',
            'hidden_count': len(hidden_assistants)
        })
        
    except Exception as e:
        return jsonify({'error': f'Chyba při skrývání asistenta: {str(e)}'}), 500

@app.route('/api/hide-multiple-assistants', methods=['POST'])
def hide_multiple_assistants():
    """
    Skryje více asistentů najednou z lokálního seznamu
    """
    try:
        data = request.get_json()
        
        if not data or 'assistant_ids' not in data:
            return jsonify({'error': 'Chybí seznam ID asistentů'}), 400
        
        assistant_ids = data['assistant_ids']
        
        if not isinstance(assistant_ids, list):
            return jsonify({'error': 'assistant_ids musí být seznam'}), 400
        
        for assistant_id in assistant_ids:
            hidden_assistants.add(assistant_id)
        
        return jsonify({
            'success': True,
            'message': f'Skryto {len(assistant_ids)} asistentů z seznamu',
            'hidden_count': len(hidden_assistants)
        })
        
    except Exception as e:
        return jsonify({'error': f'Chyba při skrývání asistentů: {str(e)}'}), 500

@app.route('/api/show-assistant', methods=['POST'])
def show_assistant():
    """
    Zobrazí skrytého asistenta zpět v seznamu
    """
    try:
        data = request.get_json()
        
        if not data or 'assistant_id' not in data:
            return jsonify({'error': 'Chybí ID asistenta'}), 400
        
        assistant_id = data['assistant_id']
        
        if assistant_id in hidden_assistants:
            hidden_assistants.remove(assistant_id)
            message = f'Asistent {assistant_id} je nyní znovu viditelný'
        else:
            message = f'Asistent {assistant_id} nebyl skrytý'
        
        return jsonify({
            'success': True,
            'message': message,
            'hidden_count': len(hidden_assistants)
        })
        
    except Exception as e:
        return jsonify({'error': f'Chyba při zobrazování asistenta: {str(e)}'}), 500

@app.route('/api/list-hidden-assistants', methods=['POST'])
def list_hidden_assistants():
    """
    Zobrazí seznam skrytých asistentů
    """
    try:
        data = request.get_json()
        
        if not data or 'openai_api_key' not in data:
            return jsonify({'error': 'Chybí OpenAI API klíč'}), 400
        
        api_key = data['openai_api_key']
        
        if not api_key:
            return jsonify({'error': 'OpenAI API klíč je povinný'}), 400
        
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'OpenAI-Beta': 'assistants=v2'
        }
        
        # Získej všechny asistenty z OpenAI
        response = requests.get('https://api.openai.com/v1/assistants', headers=headers)
        
        if response.status_code != 200:
            return jsonify({'error': f'OpenAI API chyba: {response.text}'}), 400
        
        all_assistants = response.json().get('data', [])
        
        # Najdi pouze skryté asistenty
        hidden_assistants_details = [
            assistant for assistant in all_assistants 
            if assistant['id'] in hidden_assistants
        ]
        
        return jsonify({
            'hidden_assistants': hidden_assistants_details,
            'hidden_count': len(hidden_assistants)
        })
        
    except Exception as e:
        return jsonify({'error': f'Chyba při načítání skrytých asistentů: {str(e)}'}), 500

@app.route('/api/clear-hidden-assistants', methods=['POST'])
def clear_hidden_assistants():
    """
    Zobrazí všechny skryté asistenty zpět (vymaže lokální seznam skrytých)
    """
    try:
        global hidden_assistants
        count = len(hidden_assistants)
        hidden_assistants.clear()
        
        return jsonify({
            'success': True,
            'message': f'Zobrazeno {count} dříve skrytých asistentů',
            'hidden_count': 0
        })
        
    except Exception as e:
        return jsonify({'error': f'Chyba při mazání seznamu skrytých: {str(e)}'}), 500

# NOVÁ FUNKCE PRO NORMALIZACI ČÍSLOVÁNÍ
def normalize_block_numbering(json_data):
    """
    Normalizuje číslování bloků na formát Tesla_01, Socrates_01, Narrator_01
    Převede Tesla_1 -> Tesla_01, Socrates_2 -> Socrates_02, atd.
    """
    normalized_data = {}
    
    for key, value in json_data.items():
        # Zkontroluj, jestli klíč obsahuje číslo
        if '_' in key:
            prefix, number_str = key.rsplit('_', 1)
            try:
                # Pokus se převést číslo
                number = int(number_str)
                # Vytvoř nový klíč s formátovaným číslem (01, 02, atd.)
                new_key = f"{prefix}_{number:02d}"
                normalized_data[new_key] = value
                print(f"🔧 Normalizace: {key} → {new_key}")
            except ValueError:
                # Pokud číslo nejde převést, ponech původní klíč
                normalized_data[key] = value
        else:
            # Klíč bez čísla - ponech beze změny
            normalized_data[key] = value
    
    return normalized_data

if __name__ == '__main__':
    print("🎵 AI Voice Block Combiner Backend")
    print("📂 Upload folder:", UPLOAD_FOLDER)
    print("📁 Output folder:", OUTPUT_FOLDER)
    print("🌐 Server běží na: http://localhost:5000")
    # Spuštění bez vestavěného reloaderu, aby server nespadl při běhu na pozadí
    # Používáme debug=False, protože printujeme vlastní ladicí zprávy a reloader by v pozadí způsoboval chyby termios
    app.run(debug=False, host='0.0.0.0', port=5000, use_reloader=False) 