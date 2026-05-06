from locust import HttpUser, task, between
import random

class TinyInstaUser(HttpUser):
    wait_time = between(0.5, 1.5)

    def on_start(self):
        self.user_id = f"user{random.randint(1,1000)}"

    @task
    def timeline(self):
        self.client.get(f"/api/timeline?user={self.user_id}&limit=20")