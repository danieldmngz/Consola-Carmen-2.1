import unittest
from recognition import upload_image_from_ip

class TestRecognition(unittest.TestCase):
    def test_upload_image(self):
        # Aquí puedes probar que la imagen se sube correctamente
        self.assertTrue(upload_image_from_ip())

if __name__ == "__main__":
    unittest.main()
