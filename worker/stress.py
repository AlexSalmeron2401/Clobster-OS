import multiprocessing
import time
import os

def load_cpu():
    # Identificamos el proceso para saber que está vivo
    print(f"🚀 Nucleo activado (PID: {os.getpid()})")
    while True:
        pass # Ciclo infinito de consumo de ciclos de reloj

if __name__ == "__main__":
    # Detectamos cuántos núcleos tiene tu procesador (en tu caso detectó 4)
    cores = multiprocessing.cpu_count()
    print(f"🔥 Estresando {cores} hilos... Presiona CTRL+C para detener.")
    
    processes = []
    for _ in range(cores):
        # NOTA: Usamos Process con P mayúscula
        p = multiprocessing.Process(target=load_cpu)
        p.start()
        processes.append(p)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Deteniendo el estrés...")
        for p in processes:
            p.terminate()
        print("✅ CPU liberado.")