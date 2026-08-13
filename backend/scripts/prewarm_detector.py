from app.security.detect import warm_detector

if __name__ == "__main__":
    status = warm_detector()
    print(f"Detector configured: {status.configured}")
    print(f"Detector loaded: {status.loaded}")
    print(f"Detector device: {status.device}")
    if status.failure_code:
        print(f"Detector status: {status.failure_code}")
