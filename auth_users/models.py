from django.db import models
from users.models import User
import string
import random
from django.utils import timezone
from datetime import timedelta

TEXT = string.ascii_letters + string.digits

def get_random_code(n):
    return "".join(random.choices(TEXT, k=n))


class AuthCode(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    code = models.CharField(max_length=8)
    created_at = models.DateTimeField(auto_now=True)

    @classmethod
    def create_code(cls, user):
        instance, _ = cls.objects.get_or_create(user=user)
        length = cls._meta.get_field("code").max_length
        if instance.is_expired():
            instance.update_code()
        return instance.code

    def update_code(self):
        length = self._meta.get_field("code").max_length
        self.code = get_random_code(length)
        self.save()
        return self.code

    def is_expired(self):
        now = timezone.now()
        expire_time = self.created_at + timedelta(minutes=5)
        return now > expire_time
    def is_not_expired(self):
        return not self.is_expired()

    @classmethod
    def code_is_valid(cls, user, code):
        try:
            instance = cls.objects.get(user=user)
            if instance.code == code and instance.is_not_expired():
                return True
        except cls.DoesNotExist:
            pass
        return False

    def __str__(self):
        return f"AuthCode(user={self.user.username}, code={self.code})"