
import face_recognition
import numpy as np
import cv2
from typing import Optional


class FacialService:

    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold

    def extraer_encoding(self, imagen_path: str) -> Optional[np.ndarray]:
        try:
            imagen = face_recognition.load_image_file(imagen_path)
        except Exception as e:
            raise ValueError(f"No se pudo cargar la imagen: {str(e)}")

        ubicaciones = face_recognition.face_locations(imagen, model="hog")

        if len(ubicaciones) == 0:
            return None

        encodings = face_recognition.face_encodings(imagen, ubicaciones)

        if len(encodings) == 0:
            return None

        return encodings[0]

    def comparar_con_base(self, encoding_consulta, personas_con_encodings: list):
        if not personas_con_encodings:
            return None

        personas = []
        encodings_bd = []

        for persona, encoding_lista in personas_con_encodings:
            if encoding_lista is not None:
                try:
                    encodings_bd.append(np.array(encoding_lista, dtype=np.float64))
                    personas.append(persona)
                except (ValueError, TypeError):
                    continue

        if not encodings_bd:
            return None

        encodings_array = np.array(encodings_bd)
        distancias = np.linalg.norm(encodings_array - encoding_consulta, axis=1)

        indice_mejor = np.argmin(distancias)
        distancia_mejor = distancias[indice_mejor]

        if distancia_mejor > self.threshold:
            return None

        confianza = max(0.0, 1.0 - (float(distancia_mejor) / self.threshold))

        return {
            'persona': personas[indice_mejor],
            'distancia': float(distancia_mejor),
            'confianza': round(confianza, 4)
        }

    def preprocesar_imagen(self, imagen_path: str):
        try:
            imagen = cv2.imread(imagen_path)
            if imagen is None:
                return None

            altura, ancho = imagen.shape[:2]
            max_dimension = 1200

            if max(altura, ancho) > max_dimension:
                factor = max_dimension / max(altura, ancho)
                nuevo_ancho = int(ancho * factor)
                nueva_altura = int(altura * factor)
                imagen = cv2.resize(imagen, (nuevo_ancho, nueva_altura),
                                    interpolation=cv2.INTER_AREA)

            cv2.imwrite(imagen_path, imagen, [cv2.IMWRITE_JPEG_QUALITY, 95])
            return imagen_path

        except Exception:
            return None

    def validar_imagen_tiene_rostro(self, imagen_path: str):
        try:
            imagen = face_recognition.load_image_file(imagen_path)
            ubicaciones = face_recognition.face_locations(imagen, model="hog")
            cantidad = len(ubicaciones)
            return cantidad > 0, cantidad
        except Exception:
            return False, 0

