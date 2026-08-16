import os, time, random, threading, subprocess
from queue import Queue
from pydub import AudioSegment
from pydub.silence import detect_nonsilent

MUSIC_FOLDER = "music"

def calculate_loudness(audio):
    """
    Calcula la sonoridad percibida (LUFS aproximado) del audio
    
    LUFS = Loudness Units relative to Full Scale
    Mide cómo el oído humano PERCIBE el volumen, no solo el pico más alto
    
    Esta es una aproximación simplificada del estándar EBU R128.
    Los servicios profesionales (Spotify, YouTube) usan librerías completas,
    pero esta aproximación es muy efectiva.
    
    Returns:
        float: Loudness en dBFS (aproximación de LUFS)
    """
    # Usar RMS (Root Mean Square) que se correlaciona bien con LUFS
    # RMS mide la energía promedio del audio
    samples = audio.get_array_of_samples()
    
    # Calcular RMS manualmente
    import numpy as np
    samples_array = np.array(samples).astype(float)
    rms = np.sqrt(np.mean(samples_array**2))
    
    # Convertir a dBFS
    if rms > 0:
        # 32768 es el valor máximo para audio de 16 bits
        loudness_dbfs = 20 * np.log10(rms / 32768.0)
    else:
        loudness_dbfs = -100  # Silencio
    
    return loudness_dbfs

def normalize_audio_lufs_advanced(audio, target_loudness=-5.0, true_peak=-0.5, lra_target=5):
    """
    Normalización AVANZADA con True Peak Limiting y Compresión Inteligente
    
    MODO BESTIA ACTIVADO 🔥
    
    Este método usa filtros avanzados de FFmpeg para:
    1. True Peak Limiting (TP=-1.5): Evita saturación, más margen en el crossfade
    2. Compresión dinámica inteligente: Sube partes suaves sin clipear
    3. LRA (Loudness Range): Mantiene potencia constante
    
    Target -7 LUFS = EXTREMADAMENTE ALTO
    - Spotify: -14 LUFS (100%)
    - Tu radio: -7 LUFS (316%) 🔥🔥🔥
    
    ADVERTENCIA:
    A -7 LUFS la música pierde dinámica natural. Todo suena al MÁXIMO.
    Perfecto para: EDM, Reggaetón, Pop moderno, Radio comercial agresiva
    No recomendado para: Clásica, Jazz, Acústica (pierde matices)
    
    Args:
        audio: AudioSegment a procesar
        target_loudness: Target en LUFS (por defecto -7.0 = EXTREMO)
        true_peak: Límite de pico verdadero en dB (por defecto -1.5)
        lra_target: Loudness Range target (por defecto 7 = muy comprimido, ideal para crossfade)
    
    Returns:
        AudioSegment procesado con volumen EXTREMO
    """
    import tempfile
    import subprocess
    import os
    
    # Crear archivos temporales
    temp_input = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    temp_output = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    
    try:
        # Exportar audio a WAV temporal (sin pérdida)
        audio.export(temp_input.name, format='wav')
        temp_input.close()
        
        # Construir filtro FFmpeg con loudnorm de 2 pasos (mejor calidad)
        # Paso 1: Analizar
        ffmpeg_cmd_analyze = [
            'ffmpeg',
            '-i', temp_input.name,
            '-af', f'loudnorm=I={target_loudness}:TP={true_peak}:LRA={lra_target}:print_format=json',
            '-f', 'null',
            '-'
        ]
        
        print(f"[RADIO] 📊 Analizando audio para normalización extrema...")
        
        result = subprocess.run(
            ffmpeg_cmd_analyze,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        # Extraer parámetros medidos del JSON
        import json
        import re
        
        # Buscar el JSON en la salida
        json_match = re.search(r'\{[^}]*"input_i"[^}]*\}', result.stderr)
        
        if json_match:
            stats = json.loads(json_match.group())
            measured_I = stats.get('input_i', target_loudness)
            measured_TP = stats.get('input_tp', true_peak)
            measured_LRA = stats.get('input_lra', lra_target)
            measured_thresh = stats.get('input_thresh', -70)
            
            print(f"[RADIO] 🔍 Mediciones:")
            print(f"[RADIO]    └─ Loudness actual: {measured_I} LUFS")
            print(f"[RADIO]    └─ True Peak actual: {measured_TP} dB")
            print(f"[RADIO]    └─ LRA actual: {measured_LRA}")
            
            # Paso 2: Procesar con los parámetros medidos (2-pass = mejor calidad)
            # dynaudnorm f=250: ventana más grande, más estabilidad durante el crossfade de 20s
            # loudnorm LRA=7: rango comprimido, sin baches de volumen entre canciones
            # alimiter: evita distorsión cuando se suman las frecuencias bajas del crossfade
            ffmpeg_cmd_process = [
                'ffmpeg',
                '-i', temp_input.name,
                '-af', (
                    f'loudnorm=I={target_loudness}:TP={true_peak}:LRA={lra_target}:'
                    f'measured_I={measured_I}:measured_TP={measured_TP}:'
                    f'measured_LRA={measured_LRA}:measured_thresh={measured_thresh}:'
                    f'linear=true:print_format=summary,'
                    f'alimiter=level_in=1:level_out=1:limit=0.99:attack=5:release=50'
                ),
                '-ar', '44100',
                '-y',
                temp_output.name
            ]
        else:
            print(f"[RADIO] ⚠️ No se pudo analizar, usando 1-pass")
            # Fallback a 1-pass si falla el análisis
            ffmpeg_cmd_process = [
                'ffmpeg',
                '-i', temp_input.name,
                '-af', (
                    f'loudnorm=I={target_loudness}:TP={true_peak}:LRA={lra_target}:linear=true,'
                    f'alimiter=level_in=1:level_out=1:limit=0.99:attack=5:release=50'
                ),
                '-ar', '44100',
                '-y',
                temp_output.name
            ]
        
        print(f"[RADIO] 🔥 Aplicando normalización EXTREMA...")
        print(f"[RADIO]    └─ Target: {target_loudness} LUFS (316% de Spotify)")
        print(f"[RADIO]    └─ True Peak: {true_peak} dB")
        print(f"[RADIO]    └─ LRA: {lra_target} (compresión inteligente)")
        
        result = subprocess.run(
            ffmpeg_cmd_process,
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode != 0:
            print(f"[RADIO] ❌ Error en FFmpeg: {result.stderr[:200]}")
            raise Exception("FFmpeg normalization failed")
        
        # Importar audio procesado
        temp_output.close()
        normalized_audio = AudioSegment.from_wav(temp_output.name)
        
        print(f"[RADIO] 🔊 NORMALIZACIÓN EXTREMA COMPLETADA ✅")
        print(f"[RADIO] 🔥 Volumen: -7 LUFS = 316% de Spotify = MÁXIMO PODER")
        
        return normalized_audio
        
    except subprocess.TimeoutExpired:
        print(f"[RADIO] ⚠️ Timeout en normalización, usando método básico")
        return normalize_audio_lufs_basic(audio, target_loudness=-7.0)
    
    except Exception as e:
        print(f"[RADIO] ⚠️ Error en normalización avanzada: {e}")
        print(f"[RADIO] 🔄 Fallback a método básico...")
        return normalize_audio_lufs_basic(audio, target_loudness=-7.0)
    
    finally:
        # Limpiar archivos temporales
        try:
            os.unlink(temp_input.name)
        except:
            pass
        try:
            os.unlink(temp_output.name)
        except:
            pass

def normalize_audio_lufs_basic(audio, target_loudness=-7.0):
    """
    Normalización LUFS básica (fallback) para -7 LUFS
    
    Usado si el método avanzado falla.
    Menos preciso pero funcional.
    """
    current_loudness = calculate_loudness(audio)
    gain_needed = target_loudness - current_loudness
    
    normalized = audio.apply_gain(gain_needed)
    
    # Protección anti-clipping muy agresiva
    peak_after = normalized.max_dBFS
    if peak_after > -0.1:  # Solo 0.1 dB de headroom
        overshoot = peak_after - (-0.1)
        normalized = normalized.apply_gain(-overshoot)
        final_loudness = target_loudness - overshoot
        print(f"[RADIO] 🔊 LUFS Básico: {current_loudness:.1f} → {final_loudness:.1f} LUFS (limitado por pico)")
    else:
        print(f"[RADIO] 🔊 LUFS Básico: {current_loudness:.1f} → {target_loudness:.1f} LUFS 🔥")
    
    return normalized

def normalize_audio_lufs(audio, target_loudness=-10.0):
    """
    Normalización por SONORIDAD (LUFS) - Método PROFESIONAL
    
    DEPRECATED: Esta función mantiene compatibilidad pero se recomienda
    usar normalize_audio_lufs_advanced() para mejor calidad.
    
    Target ajustado a -10 LUFS para VOLUMEN MÁS ALTO
    
    SUPERIOR a Peak Normalization porque:
    - Mide cómo el OÍDO HUMANO percibe el volumen
    - Todas las canciones suenan al mismo volumen PERCIBIDO
    - Usado por: Spotify (-14 LUFS), YouTube (-14 LUFS), Apple Music (-16 LUFS)
    
    Target -10 LUFS = MÁS ALTO que Spotify (perfecto para radio online)
    
    DIFERENCIA vs Peak Normalization:
    - Peak: "¿Cuál es el punto más alto?" → Puede sonar inconsistente
    - LUFS: "¿Qué tan fuerte SUENA en promedio?" → Volumen consistente
    
    Ejemplo:
    - Canción A: Pico en 0dB, pero promedio bajo → Suena bajita con Peak Norm
    - Canción B: Pico en -3dB, pero promedio alto → Suena fuerte con Peak Norm
    - Con LUFS: AMBAS suenan igual de fuerte ✅
    
    Args:
        audio: AudioSegment a normalizar
        target_loudness: Target en LUFS (por defecto -10.0 = MÁS ALTO)
    
    Returns:
        AudioSegment normalizado por sonoridad
    """
    # Calcular loudness actual
    current_loudness = calculate_loudness(audio)
    
    # Calcular cuánta ganancia necesitamos
    gain_needed = target_loudness - current_loudness
    
    # Aplicar ganancia
    normalized = audio.apply_gain(gain_needed)
    
    # PROTECCIÓN ANTI-CLIPPING:
    # Si el pico resultante supera 0 dBFS, reducir para evitar distorsión
    peak_after = normalized.max_dBFS
    if peak_after > -0.3:  # Dejar solo 0.3 dB de headroom (más agresivo)
        overshoot = peak_after - (-0.3)
        normalized = normalized.apply_gain(-overshoot)
        final_loudness = target_loudness - overshoot
        print(f"[RADIO] 🔊 LUFS Normalization: {current_loudness:.1f} → {final_loudness:.1f} LUFS (ganancia: {gain_needed:.1f} dB, limitado por pico)")
    else:
        print(f"[RADIO] 🔊 LUFS Normalization: {current_loudness:.1f} → {target_loudness:.1f} LUFS (ganancia: {gain_needed:.1f} dB) 🔥 ALTO")
    
    return normalized

def normalize_audio():
    """
    DEPRECATED: Usar normalize_audio_lufs() en su lugar
    Esta función se mantiene por compatibilidad pero ya no se usa
    """
    pass
    return normalized

def detect_leading_silence(audio, silence_threshold=-30.0, chunk_size=10):
    """
    Detecta silencio al inicio del audio.
    silence_threshold=-30dB: agresivo, elimina siseo sin tomar el "aire" final como música.
    """
    trim_ms = 0
    while trim_ms < len(audio):
        chunk = audio[trim_ms:trim_ms + chunk_size]
        if chunk.dBFS > silence_threshold:
            break
        trim_ms += chunk_size
    return trim_ms

def strip_silence(audio, silence_thresh=-30):
    """
    Elimina silencios usando detect_leading_silence sobre el audio invertido.
    
    POR QUÉ ESTE MÉTODO PARA EL CROSSFADE:
    - Detecta el silencio REAL al final invirtiendo el audio (audio.reverse())
    - Con -30dB, corta el siseo residual sin confundirlo con música
    - Garantiza que el crossfade de 20s sea música pura contra música pura
    - Un umbral muy bajo (-50) tomaba el "aire" final como música → siguiente canción entraba antes
    
    Args:
        audio: AudioSegment a procesar
        silence_thresh: Umbral en dB (por defecto -30dB = agresivo pero preciso)
    
    Returns:
        AudioSegment sin silencios al inicio/final
    """
    duration = len(audio)
    
    # 1. Silencio al INICIO
    start_trim = detect_leading_silence(audio, silence_threshold=silence_thresh)
    
    # 2. Silencio al FINAL: invertir el audio y detectar el inicio del invertido
    audio_reversed = audio.reverse()
    end_trim = detect_leading_silence(audio_reversed, silence_threshold=silence_thresh)
    
    # 3. Cortar ambos extremos
    trimmed = audio[start_trim:duration - end_trim]
    
    removed_start = start_trim / 1000
    removed_end = end_trim / 1000
    total_removed = removed_start + removed_end
    
    if total_removed > 0.1:
        print(f"[RADIO] ✂️ SILENCIO CORTADO (-30dB, reverse): {total_removed:.2f}s total")
        print(f"[RADIO]    └─ Inicio: {removed_start:.2f}s | Final: {removed_end:.2f}s")
        print(f"[RADIO] 📏 Audio: {duration/1000:.1f}s → {len(trimmed)/1000:.1f}s (limpio ✨)")
    else:
        print(f"[RADIO] ✅ Audio ya limpio (sin silencios detectables)")
    
    return trimmed

def format_seconds(seconds):
    minutes = seconds // 60
    remaining_seconds = seconds % 60
    return f"{minutes}:{remaining_seconds:02d}"

class RadioStation:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RadioStation, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self):
        if self.initialized:
            return
        self.queue_requests = Queue()
        self.queue_local = []
        self._already_running = False
        self.temp_queue_folder = "temp_queue"
        if not os.path.exists(self.temp_queue_folder):
            os.makedirs(self.temp_queue_folder)
        self.running = True
        self.current_track = None
        self.skip_current = False
        self.owner_id = "64dc252537db1cdb8e202d8d"
        self.bot_wallet = 0
        self.bot_id = None
        self.played_indices = []
        self.bot_instance = None
        self.stream_played_track = None
        self.paused = False
        self.previous_track = None
        self.history = []
        self.track_start_time = time.time()
        self.pre_buffer = True
        self.initialized = True
        self.crossfade_seconds = 20
        self.current_duration = 0
        self.next_track_preloaded = None
        self.preloading = False
        self.next_track_consumed = False
        self._preloaded_index = None
        self._preloaded_audio = None
        self._preloaded_mp3 = None
        self._preloaded_mp3_idx = None
        
        self.audio_buffer = Queue(maxsize=50)
        self.clients = []
        self._last_chunks = []  # Buffer para nuevos clientes

    def load_local_music(self, mega_instance=None):
        """Carga la música desde la carpeta local music/."""
        try:
            if not os.path.exists(MUSIC_FOLDER):
                os.makedirs(MUSIC_FOLDER)

            extensions = {'.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac', '.opus'}
            self.queue_local = []

            for filename in sorted(os.listdir(MUSIC_FOLDER)):
                if os.path.splitext(filename.lower())[1] in extensions:
                    filepath = os.path.join(MUSIC_FOLDER, filename)
                    self.queue_local.append({
                        "file": filepath,
                        "name": os.path.splitext(filename)[0],
                        "user": "Local",
                        "username": "System",
                        "duration": 0,
                    })

            print(f"[RADIO] {len(self.queue_local)} canciones cargadas desde {MUSIC_FOLDER}/")
        except Exception as e:
            print(f"[RADIO] Error cargando música local: {e}")

    def add_to_queue(self, track):
        print(f"[RADIO] 📥 Agregando pedido: {track['name']}")
        self.queue_requests.put(track)

    def _announce_now_playing(self, track):
        """Publica en Highrise la canción que acaba de entrar al aire."""
        print(f"[RADIO] ▶️ REPRODUCIENDO_AHORA: {track['name']}")
        if self.bot_instance:
            try:
                import asyncio as _asyncio
                duration_str = format_seconds(track.get("duration", 0))
                requested_by = track.get("username", "System")
                msg = (
                    f"<#90EE90>🎧:Ahora en reproducción:\n"
                    f"<#90EE90>📀:{track['name']}\n"
                    f"<#90EE90>⏱️: Duración: ({duration_str})\n"
                    f"<#90EE90>👤Solicitado por: @{requested_by}"
                )
                if hasattr(self.bot_instance, "highrise") and self.bot_instance.highrise:
                    _asyncio.run_coroutine_threadsafe(
                        self.bot_instance.highrise.chat(msg),
                        self.bot_instance.loop
                    )
            except Exception as e:
                print(f"[RADIO] Error enviando now-playing: {e}")

    def _broadcast_chunk(self, chunk):
        """Entrega un bloque al stream HTTP y conserva un buffer corto."""
        dead = []
        for q in self.clients:
            try:
                q.put_nowait(chunk)
            except Exception:
                dead.append(q)
        for q in dead:
            if q in self.clients:
                self.clients.remove(q)
        self._last_chunks.append(chunk)
        if len(self._last_chunks) > 20:
            self._last_chunks.pop(0)

    def _stream_remote_track(self, track):
        """
        Reproduce una URL temporal de YouTube directamente con FFmpeg.

        FFmpeg transforma el audio en MP3 por stdout y los bytes se envían a
        los oyentes conforme llegan. Los fades se aplican dentro de FFmpeg;
        no se crea ningún archivo temporal.
        """
        stream_url = track.get("stream_url")
        if not stream_url:
            raise ValueError("La canción no tiene stream_url")

        # Mantener el mismo tiempo configurado para el crossfade de la radio.
        # En un stream remoto no podemos cargar la canción completa para
        # mezclarla en memoria, así que aplicamos fade-in/out directamente
        # mientras FFmpeg la convierte y la envía.
        duration = float(track.get("duration") or 0)
        fade_seconds = min(float(self.crossfade_seconds), duration / 2) if duration else 0
        audio_filters = []
        if fade_seconds > 0:
            fade_start = max(0, duration - fade_seconds)
            audio_filters.extend([
                f"afade=t=in:st=0:d={fade_seconds:.3f}:curve=tri",
                f"afade=t=out:st={fade_start:.3f}:d={fade_seconds:.3f}:curve=tri",
            ])

        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-nostdin",
            "-re",
            "-i", stream_url,
            "-vn",
            "-ac", "2",
            "-ar", "44100",
        ]
        if audio_filters:
            command.extend(["-af", ",".join(audio_filters)])
        command.extend([
            "-c:a", "libmp3lame",
            "-b:a", "192k",
            "-flush_packets", "1",
            "-f", "mp3",
            "pipe:1",
        ])
        print(f"[RADIO] 📡 Abriendo stream remoto: {track['name']}")
        if audio_filters:
            print(f"[RADIO] 🎚️ Fade remoto activo: {fade_seconds:.1f}s entrada/salida")
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )

        try:
            while self.running and not self.skip_current:
                while self.paused and self.running and not self.skip_current:
                    time.sleep(0.1)

                chunk = process.stdout.read(16 * 1024)
                if not chunk:
                    break
                self._broadcast_chunk(chunk)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
            if process.returncode not in (None, 0) and self.running and not self.skip_current:
                error = process.stderr.read().decode("utf-8", errors="replace")[-300:]
                print(f"[RADIO] ⚠️ FFmpeg terminó con error: {error}")
            else:
                print(f"[RADIO] ✅ Stream remoto finalizado: {track['name']}")

    def start(self):
        if hasattr(self, "_already_running") and self._already_running:
            print("[RADIO] ⚠️ El bucle de radio ya está activo.")
            return
        self._already_running = True
        
        local_index = 0
        import io

        if not self.queue_local:
            self.load_local_music()

        while self.running:
            track = None

            # Prioridad: Cola de pedidos
            if not self.queue_requests.empty():
                track = self.queue_requests.get()
                print(f"[RADIO] ⚡ Reproduciendo pedido: {track['name']}")
            elif self.queue_local:
                if local_index >= len(self.queue_local):
                    local_index = 0
                track = self.queue_local[local_index]
                local_index += 1
                print(f"[RADIO] 📂 Reproduciendo local ({local_index}/{len(self.queue_local)}): {track['name']}")

            if track:
                if self.current_track:
                    self.previous_track = self.current_track
                    self.history.append(self.current_track)
                    if len(self.history) > 20:
                        self.history = self.history[-20:]
                
                self.current_track = track
                self.current_duration = track.get("duration", 0)
                self.stream_played_track = None 
                self.skip_current = False
                self.preloading = False
                
                try:
                    # Las solicitudes de YouTube se reproducen directamente
                    # desde su URL temporal; no pasan por AudioSegment ni se
                    # guardan en music/.
                    if track.get("stream_url"):
                        self.track_start_time = time.time()
                        self.current_duration = track.get("duration", 0)
                        self._announce_now_playing(track)
                        self._stream_remote_track(track)
                        self.current_track = None
                        continue

                    t_start = time.time()

                    # ── 1. CARGAR AUDIO ──────────────────────────────────────
                    # Si esta canción ya fue pre-cargada por el tail anterior, reutilizarla
                    current_idx   = local_index - 1  # local_index ya fue incrementado
                    preloaded_audio = getattr(self, '_preloaded_audio', None)
                    preloaded_idx   = getattr(self, '_preloaded_index', None)

                    if preloaded_audio is not None and preloaded_idx == current_idx:
                        # Los primeros 20s ya sonaron en el crossfade → cortar
                        crossfade_cut = self.crossfade_seconds * 1000
                        audio = preloaded_audio[crossfade_cut:]
                        self._preloaded_audio = None
                        self._preloaded_index = None
                        print(f"[RADIO] ⚡ Audio pre-cargado, saltando primeros {self.crossfade_seconds}s (ya sonaron en crossfade)")
                    else:
                        print(f"[RADIO] ⏬ Cargando audio: {track['name']}...")
                        audio = AudioSegment.from_file(track["file"])
                        print(f"[RADIO] ✅ Audio cargado en {time.time()-t_start:.1f}s")

                        # ── 2. CONVERTIR FORMATO ─────────────────────────────
                        audio = audio.set_frame_rate(44100).set_channels(2).set_sample_width(2)

                        # ── 3. ELIMINAR SILENCIOS ────────────────────────────
                        t_sil = time.time()
                        audio = strip_silence(audio, silence_thresh=-30)
                        print(f"[RADIO]    └─ strip_silence: {time.time()-t_sil:.1f}s")

                        # ── 4. NORMALIZACIÓN FFmpeg ──────────────────────────
                        t_norm = time.time()
                        audio = normalize_audio_lufs_advanced(
                            audio,
                            target_loudness=-5.0,
                            true_peak=-0.5,
                            lra_target=5
                        )
                        print(f"[RADIO]    └─ normalize: {time.time()-t_norm:.1f}s")
                        print(f"[RADIO] ⏱️ Procesamiento total: {time.time()-t_start:.1f}s")

                    duration_ms = len(audio)
                    if track.get("duration") == 0:
                        track["duration"] = int(duration_ms / 1000)

                    # ── 5. NOW PLAYING ───────────────────────────────────────
                    self._announce_now_playing(track)

                    # ── 6. EXPORTAR EN BACKGROUND + PRE-CARGAR SIGUIENTE ─────
                    # Nueva arquitectura sin pausas:
                    # - Thread A: exporta la canción actual a MP3 en background
                    # - Thread B: pre-carga y procesa la canción siguiente en paralelo
                    # - Thread C: cuando B termina, construye el crossfade (20s)
                    # - Stream: empieza a leer el MP3 de A en cuanto el primer chunk esté disponible
                    # - Al final del stream: pega el crossfade de C sin ningún wait
                    crossfade_ms = self.crossfade_seconds * 1000
                    bytes_per_500ms = 20000

                    if len(audio) < 1000:
                        print("[RADIO] ⚠️ Audio demasiado corto, ignorando...")
                        continue

                    # Exportar la canción actual en un thread aparte
                    # El stream empieza a leer cuando el export termina
                    mp3_ready    = threading.Event()
                    mp3_holder   = []  # [bytes]

                    def export_current():
                        buf = io.BytesIO()
                        try:
                            audio.export(buf, format="mp3", bitrate="320k")
                        except Exception:
                            audio.export(buf, format="mp3", bitrate="160k")
                        mp3_holder.append(buf.getvalue())
                        mp3_ready.set()
                        print(f"[RADIO] 💿 Export listo: {len(mp3_holder[0])//1024}KB")

                    export_thread = threading.Thread(target=export_current, daemon=True)
                    export_thread.start()

                    # Thread B: pre-cargar siguiente canción en paralelo con el export
                    next_audio       = None
                    next_audio_ready = threading.Event()

                    def preload_next():
                        nonlocal next_audio
                        if not self.queue_requests.empty() or not self.queue_local:
                            next_audio_ready.set()
                            return
                        try:
                            idx = local_index if local_index < len(self.queue_local) else 0
                            nt  = self.queue_local[idx]
                            t_pre = time.time()
                            print(f"[RADIO] ⏳ Pre-cargando: {nt['name']}...")
                            na = AudioSegment.from_file(nt["file"])
                            na = na.set_frame_rate(44100).set_channels(2).set_sample_width(2)
                            na = strip_silence(na, silence_thresh=-30)
                            na = normalize_audio_lufs_advanced(na, target_loudness=-5.0, true_peak=-0.5, lra_target=5)
                            next_audio           = na
                            self._preloaded_audio = na
                            self._preloaded_index = idx
                            print(f"[RADIO] ✅ Pre-carga lista en {time.time()-t_pre:.1f}s: {nt['name']}")
                        except Exception as e:
                            print(f"[RADIO] ⚠️ Error pre-carga: {e}")
                        finally:
                            next_audio_ready.set()

                    preload_thread = threading.Thread(target=preload_next, daemon=True)
                    preload_thread.start()

                    # Thread C: cuando la pre-carga esté lista, construir el crossfade
                    tail_data  = []
                    tail_ready = threading.Event()

                    def prepare_tail():
                        try:
                            next_audio_ready.wait(timeout=120)
                            if next_audio and duration_ms > crossfade_ms:
                                fadeout = audio[-crossfade_ms:].fade_out(crossfade_ms)
                                fadein  = next_audio[:crossfade_ms]
                                mixed   = fadeout.overlay(fadein)
                                buf     = io.BytesIO()
                                mixed.export(buf, format="mp3", bitrate="320k")
                                tail_data.append(buf.getvalue())
                                print(f"[RADIO] ✅ Crossfade 20s listo (+6dB)")
                        except Exception as e:
                            print(f"[RADIO] ⚠️ Error crossfade: {e}")
                        finally:
                            tail_ready.set()

                    tail_thread = threading.Thread(target=prepare_tail, daemon=True)
                    tail_thread.start()

                    # El export ocurre en background. Esperamos aquí solo la primera
                    # vez (canción 1). Para canción 2 en adelante, el export ya terminó
                    # mientras la canción anterior estaba haciendo stream.
                    preloaded_mp3 = getattr(self, '_preloaded_mp3', None)
                    preloaded_mp3_idx = getattr(self, '_preloaded_mp3_idx', None)
                    current_idx = local_index - 1

                    if preloaded_mp3 is not None and preloaded_mp3_idx == current_idx:
                        # MP3 ya exportado de la iteración anterior → 0 segundos de espera
                        mp3_data = preloaded_mp3
                        self._preloaded_mp3 = None
                        self._preloaded_mp3_idx = None
                        print(f"[RADIO] ⚡ MP3 pre-exportado disponible, stream inmediato")
                    else:
                        # Primera canción o fallback: esperar el export
                        mp3_ready.wait()
                        mp3_data = mp3_holder[0]
                        print(f"[RADIO] 💿 MP3 listo, iniciando stream")

                    # Exportar la siguiente canción en background mientras hacemos stream
                    # Para que cuando llegue su turno, su MP3 ya esté listo
                    def export_next_mp3():
                        try:
                            next_audio_ready.wait(timeout=120)
                            if next_audio:
                                idx = getattr(self, '_preloaded_index', None)
                                buf = io.BytesIO()
                                try:
                                    next_audio.export(buf, format="mp3", bitrate="320k")
                                except Exception:
                                    next_audio.export(buf, format="mp3", bitrate="160k")
                                self._preloaded_mp3     = buf.getvalue()
                                self._preloaded_mp3_idx = idx
                                print(f"[RADIO] 💿 MP3 siguiente pre-exportado ({len(self._preloaded_mp3)//1024}KB)")
                        except Exception as e:
                            print(f"[RADIO] ⚠️ Error pre-export MP3: {e}")

                    threading.Thread(target=export_next_mp3, daemon=True).start()

                    self.next_track_consumed = False

                    # 🚀 STREAM CONTINUO: canción completa + crossfade pegado al final
                    # Cuando el loop llega al último chunk, el crossfade ya lleva
                    # minutos preparándose → se pega inmediatamente sin ningún gap.
                    t0             = time.time()
                    n              = 0
                    streaming_data = mp3_data
                    tail_appended  = False

                    for i in range(0, len(streaming_data), bytes_per_500ms):
                        while self.paused:
                            time.sleep(0.1)
                            t0 += 0.1
                        if not self.running or self.skip_current:
                            break

                        # Último chunk de la canción: pegar crossfade si está listo
                        if not tail_appended and i + bytes_per_500ms >= len(streaming_data):
                            tail_ready.wait(timeout=3)
                            if tail_data:
                                streaming_data = streaming_data + tail_data[0]
                                tail_appended  = True
                                print(f"[RADIO] 🎚️ Crossfade pegado, stream continúa sin pausa")

                        chunk = streaming_data[i:i + bytes_per_500ms]
                        self._broadcast_chunk(chunk)
                        n  += 1
                        gap = (t0 + n * 0.5) - time.time()
                        if gap > 0:
                            time.sleep(gap)
                        elif gap < -1.0:
                            t0 = time.time() - n * 0.5

                    # Evitar que el buffer se sature
                    if self.audio_buffer.full():
                        try:
                            self.audio_buffer.get_nowait()
                        except:
                            pass

                except Exception as e:
                    print(f"[RADIO] ⚠️ Error en playback: {e}")
                    import traceback
                    traceback.print_exc()
                
                # Las canciones quedan en music/ para futuras reproducciones — sin limpieza necesaria

                self.current_track = None
            else:
                time.sleep(1)

    def generate_stream(self):
        from queue import Queue as ClientQueue
        my_queue = ClientQueue(maxsize=100) 
        self.clients.append(my_queue)
        print(f"[RADIO] 📡 Nuevo cliente conectado. Total: {len(self.clients)}")
        
        try:
            # 🔧 BUFFER INICIAL: Enviar últimos chunks INMEDIATAMENTE para evitar silencio
            if self._last_chunks:
                print(f"[RADIO] ⚡ Enviando buffer inicial ({len(self._last_chunks)} chunks = ~{len(self._last_chunks)*0.5}s)")
                for chunk in self._last_chunks:
                    yield chunk
            else:
                # Si no hay buffer aún, esperar al primer chunk
                print(f"[RADIO] ⏳ Esperando primer chunk...")
            
            # Continuar con stream normal
            while self.running:
                try:
                    data = my_queue.get(timeout=10)
                    yield data
                except:
                    # Si timeout, continuar esperando
                    pass
        except Exception as e:
            print(f"[RADIO] ⚠️ Error en stream: {e}")
        finally:
            if my_queue in self.clients:
                self.clients.remove(my_queue)
            print(f"[RADIO] 📡 Cliente desconectado. Quedan: {len(self.clients)}")
