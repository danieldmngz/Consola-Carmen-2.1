# Proyecto de Reconocimiento de Matrículas

Este proyecto captura imágenes de matrículas de vehículos desde una cámara IP y las procesa para identificar la matrícula utilizando una API de carmen. Los datos obtenidos se guardan en un archivo CSV, y las imágenes se almacenan localmente o BD.

## Requisitos

Asegúrate de tener instalados los siguientes paquetes de Python:

- `requests`
- `carmen_cloud_client`
- `pyinstaller`

Puedes instalarlos usando `pip`:

```bash
pip install requests carmen_cloud_client pyinstaller
pyinstaller --onefile --add-data "settings.config;." recognition.py
