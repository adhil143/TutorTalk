from django.db import models
from django.contrib.auth.models import User

class Notebook(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notebooks')
    title = models.CharField(max_length=255)
    theme_color = models.CharField(max_length=50, default='cyan')  # 'cyan', 'emerald', 'purple', 'orange', 'amber'
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class Note(models.Model):
    notebook = models.ForeignKey(Notebook, on_delete=models.CASCADE, related_name='notes')
    title = models.CharField(max_length=255)
    uploaded_file = models.FileField(upload_to='notes/')
    content = models.TextField(blank=True, null=True)
    summary = models.TextField(blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class Flashcard(models.Model):
    note = models.ForeignKey(Note, on_delete=models.CASCADE, related_name='flashcards')
    question = models.TextField()
    answer = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Flashcard for {self.note.title}: {self.question[:30]}"

class Quiz(models.Model):
    note = models.ForeignKey(Note, on_delete=models.CASCADE, related_name='quizzes')
    question = models.TextField()
    option_a = models.CharField(max_length=255)
    option_b = models.CharField(max_length=255)
    option_c = models.CharField(max_length=255)
    option_d = models.CharField(max_length=255)
    correct_option = models.CharField(max_length=1)  # 'A', 'B', 'C', or 'D'
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Quiz for {self.note.title}: {self.question[:30]}"

class ChatMessage(models.Model):
    notebook = models.ForeignKey(Notebook, on_delete=models.CASCADE, related_name='chat_messages')
    role = models.CharField(max_length=20)  # 'user' or 'assistant'
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.role.capitalize()} message for notebook at {self.created_at}"
