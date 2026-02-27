#!/bin/bash
# render-build.sh

# Crear archivo de swap para aumentar memoria virtual
echo "Creando archivo de swap..."
fallocate -l 4G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
swapon --show
free -h

# Instalar dependencias del sistema
echo "Instalando dependencias del sistema..."
apt-get update
apt-get install -y build-essential cmake pkg-config
apt-get install -y libx11-dev libatlas-base-dev
apt-get install -y libgtk-3-dev libboost-python-dev

# Actualizar pip
echo "Actualizando pip..."
pip install --upgrade pip setuptools wheel

# Instalar numpy primero
echo "Instalando numpy..."
pip install numpy==1.24.3

# Instalar dlib con flags de optimización
echo "Instalando dlib (esto puede tomar varios minutos)..."
pip install --no-cache-dir dlib==19.24.2

# Instalar el resto de dependencias
echo "Instalando resto de dependencias..."
pip install --no-cache-dir -r requirements.txt

# Desactivar swap (opcional)
swapoff /swapfile
rm /swapfile

echo "Build completado!"
