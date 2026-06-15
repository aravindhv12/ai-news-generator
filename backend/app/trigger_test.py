import requests
import time
import sys

BASE_URL = "http://localhost:8000"

def test_flow():
    # 1. Login
    print("Attempting to login...")
    try:
        response = requests.post(
            f"{BASE_URL}/auth/login",
            data={"username": "admin", "password": "change_me"}
        )
        if response.status_code != 200:
            print(f"Login failed: {response.status_code} - {response.text}")
            return
        
        token = response.json().get("access_token")
        print("Login successful! Token acquired.")
    except Exception as e:
        print(f"Error during login: {e}")
        return

    headers = {"Authorization": f"Bearer {token}"}

    # 2. Check initial status
    try:
        status_resp = requests.get(f"{BASE_URL}/posts/pipeline-status", headers=headers)
        print(f"Initial pipeline status: {status_resp.json()}")
    except Exception as e:
        print(f"Error getting initial status: {e}")
        return

    # 3. Trigger scan
    print("Triggering pipeline scan...")
    try:
        trigger_resp = requests.post(f"{BASE_URL}/posts/trigger-pipeline", headers=headers)
        print(f"Trigger response: {trigger_resp.json()}")
    except Exception as e:
        print(f"Error triggering scan: {e}")
        return

    # 4. Poll status
    print("Starting status polling...")
    while True:
        try:
            status_resp = requests.get(f"{BASE_URL}/posts/pipeline-status", headers=headers)
            status_data = status_resp.json()
            print(f"Status: {status_data['status']}, Error: {status_data['last_error']}")
            
            if status_data["status"] != "running":
                break
        except Exception as e:
            print(f"Error polling status: {e}")
            break
        
        time.sleep(2)

    # 5. Fetch posts
    print("Pipeline finished. Fetching generated posts...")
    try:
        posts_resp = requests.get(f"{BASE_URL}/posts/", headers=headers)
        posts = posts_resp.json()
        print(f"Posts count: {len(posts)}")
        for idx, post in enumerate(posts[:5]): # Print top 5
            print(f"\nPost {idx + 1}:")
            print(f"  ID: {post.get('id')}")
            print(f"  Headline: {post.get('headline')}")
            print(f"  Summary: {post.get('summary')}")
            print(f"  Image URL: {post.get('image_url')}")
            print(f"  Status: {post.get('status')}")
    except Exception as e:
        print(f"Error fetching posts: {e}")

if __name__ == "__main__":
    test_flow()
