# INVASION_PYTHON

Videojuego arcade de ciencia ficción desarrollado en Python con Pygame CE. Defiende la Tierra de la invasión Xhar'Kor, supera cinco niveles y utiliza tres armas.

## Requisitos

- Python 3.10 o superior
- pygame-ce

## Instalación y ejecución

```bash
python -m venv .venv
```

Activa el entorno virtual y luego instala las dependencias y ejecuta el juego:

```bash
python -m pip install -r requirements.txt
python Invasio.py
```

En Windows, activa el entorno con `.venv\Scripts\activate`. En macOS o Linux, usa `source .venv/bin/activate`.

## Controles

- **Mover:** flechas o WASD
- **Ráfaga:** W o Espacio
- **Misil:** E
- **Láser:** Q
- **Pausar:** P
- **Silenciar/activar sonido:** M
- **Iniciar o continuar:** Espacio o Enter, según la pantalla
- **Salir:** Esc

## Recursos

Los recursos visuales y de audio están en `data/`. El juego puede ejecutarse sin ellos; cuando faltan, usa fondos y efectos visuales generados por el propio juego y omite audio/imágenes no disponibles.

## Estructura

```text
INVASION_PYTHON/
├── Invasio.py
├── requirements.txt
├── README.md
├── .gitignore
└── data/
```
