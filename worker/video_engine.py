import sys
import subprocess
import os

def get_ffmpeg_command(input_file, output_file, action):
    # Diccionario de resoluciones solicitadas
    res_map = {
        "video_360p": "scale=-2:360",
        "video_480p": "scale=-2:480",
        "video_720p": "scale=-2:720",
        "video_900p": "scale=-2:900",
        "video_1080p": "scale=-2:1080",
        "video_1440p": "scale=-2:1440"
    }
    
    vf = res_map.get(action, "scale=-2:720")
    
    # Comando optimizado: libx264 para compatibilidad y fast para velocidad
    return [
        "ffmpeg", "-y", "-i", input_file,
        "-vf", vf, "-c:v", "libx264", "-crf", "23",
        "-preset", "faster", "-c:a", "copy", output_file
    ]

if __name__ == "__main__":
    # Argumentos: [1]input, [2]output, [3]action
    if len(sys.argv) < 4:
        sys.exit(1)

    in_f, out_f, act = sys.argv[1], sys.argv[2], sys.argv[3]
    
    # Crear carpeta de salida si no existe
    os.makedirs(os.path.dirname(out_f), exist_ok=True)
    
    cmd = get_ffmpeg_command(in_f, out_f, act)
    
    try:
        # Ejecutamos y esperamos
        process = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        sys.exit(process.returncode)
    except Exception as e:
        print(f"Error en motor de video: {e}")
        sys.exit(1)