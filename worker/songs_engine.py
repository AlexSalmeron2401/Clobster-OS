import sys
import subprocess
import os

def get_audio_command(input_file, output_file, action):
    # Diccionario maestro de formatos y códecs
    configs = {
        # MP3 estándar
        "audio_mp3_320": ["-c:a", "libmp3lame", "-b:a", "320k"],
        "audio_mp3_128": ["-c:a", "libmp3lame", "-b:a", "128k"],
        # Apple / Estándar móvil
        "audio_aac": ["-c:a", "aac", "-b:a", "256k", "-ar", "44100", "-ac", "2"],
        "audio_m4a": ["-c:a", "aac", "-b:a", "320k"],
        # Formatos Abiertos / Web
        "audio_ogg": ["-c:a", "libvorbis", "-q:a", "6"],
        "audio_opus": ["-c:a", "libopus", "-b:a", "128k"],
        # Alta Fidelidad (Lossless)
        "audio_flac": ["-c:a", "flac", "-compression_level", "5"],
        "audio_aiff": ["-c:a", "pcm_s16be"], # Formato AIFF sin pérdida
        # Simulación de LDAC (Hi-Res Audio 96kHz/24-bit)
        "audio_hires_sim": ["-c:a", "flac", "-bits_per_raw_sample", "24", "-ar", "96000"],
        # Formatos Legados / Voz
        "audio_amr": ["-c:a", "libopencore_amrnb", "-ar", "8000", "-ab", "12.2k", "-ac", "1"]
    }
    
    audio_params = configs.get(action, configs["audio_mp3_320"])
    
    return ["ffmpeg", "-y", "-i", input_file] + audio_params + [output_file]

if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(1)

    in_f, out_f, act = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(os.path.dirname(out_f), exist_ok=True)
    
    cmd = get_audio_command(in_f, out_f, act)
    
    try:
        # Ejecución del subproceso FFmpeg
        process = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        sys.exit(process.returncode)
    except Exception as e:
        print(f"Error en motor de audio: {e}")
        sys.exit(1)