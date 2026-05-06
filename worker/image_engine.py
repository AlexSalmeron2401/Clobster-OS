import sys
import os
from PIL import Image, ImageOps, ImageFilter

def apply_filter(img, action):
    if action == "img_gray":
        return ImageOps.grayscale(img)
    elif action == "img_sepia":
        # Filtro sepia manual usando una matriz de color
        sepia_data = [
            0.393, 0.769, 0.189, 0,
            0.349, 0.686, 0.168, 0,
            0.272, 0.534, 0.131, 0
        ]
        return img.convert("RGB").point(lambda p: p).convert("RGB", sepia_data)
    elif action == "img_blur":
        return img.filter(ImageFilter.GaussianBlur(radius=5))
    elif action == "img_contour":
        return img.filter(ImageFilter.CONTOUR)
    elif action == "img_sharpen":
        return img.filter(ImageFilter.SHARPEN)
    return img

def resize_img(img, action):
    # Diccionario de resoluciones basadas en altura (16:9)
    resoluciones = {
        "img_360p": (640, 360),
        "img_720p": (1280, 720),
        "img_1080p": (1920, 1080),
        "img_2k": (2560, 1440),
        "img_4k": (3840, 2160)
    }
    
    if action in resoluciones:
        # Usamos Lanczos para máxima calidad al reescalar (especialmente a 4K)
        return img.resize(resoluciones[action], Image.Resampling.LANCZOS)
    return img

if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(1)

    in_f, out_f, act = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(os.path.dirname(out_f), exist_ok=True)

    try:
        with Image.open(in_f) as img:
            # Primero aplicamos redimensionamiento (si aplica)
            img = resize_img(img, act)
            # Luego aplicamos filtros (si aplica)
            img = apply_filter(img, act)
            
            # Guardamos (convertimos a RGB por si es PNG con transparencia y guardamos en JPG/WebP)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(out_f, quality=95)
            
        sys.exit(0)
    except Exception as e:
        print(f"Error procesando imagen: {e}")
        sys.exit(1)