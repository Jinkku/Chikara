from django.db import models

class Message(models.Model):
    room   = models.CharField(max_length=100)
    author = models.CharField(max_length=100)
    body   = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.room}] {self.author}: {self.body[:40]}"