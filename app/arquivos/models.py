from django.db import models

class Arquivo(models.Model):
    nome = models.CharField(max_length=255)
    arquivo = models.FileField(upload_to="uploads/")
    enviado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nome
