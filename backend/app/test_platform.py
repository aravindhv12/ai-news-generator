import requests
import time
import sys

BASE_URL = "http://localhost:8000"

def run_tests():
    print("====================================================")
    print("STARTING END-TO-END INTEGRATION TESTING")
    print("====================================================")

    # 1. Login
    print("\n--- Test 1: Authentication ---")
    try:
        resp = requests.post(
            f"{BASE_URL}/auth/login",
            data={"username": "admin", "password": "change_me"}
        )
        if resp.status_code != 200:
            print(f"FAIL: Login failed: {resp.status_code} - {resp.text}")
            sys.exit(1)
        token = resp.json().get("access_token")
        print("PASS: Authentication successful.")
    except Exception as e:
        print(f"FAIL: Authentication error: {e}")
        sys.exit(1)

    headers = {"Authorization": f"Bearer {token}"}
    cron_headers = {"Authorization": "Bearer super-secret-key"} # Using JWT_SECRET as cron authorization fallback key

    # Helper function to poll dashboard status
    def poll_pipeline_idle():
        print("Waiting for pipeline to become idle...")
        for _ in range(30):
            d_resp = requests.get(f"{BASE_URL}/api/dashboard", headers=headers)
            pipeline_state = d_resp.json().get("pipeline", {})
            if pipeline_state.get("status") == "idle":
                print(f"Pipeline is idle. Last error: {pipeline_state.get('last_error')}")
                return
            time.sleep(2)
        print("FAIL: Pipeline stuck in running state.")
        sys.exit(1)

    # Ensure pipeline is idle first
    poll_pipeline_idle()

    # 2. Get Initial Stats
    print("\n--- Test 2: Initial Dashboard Stats ---")
    dash_resp = requests.get(f"{BASE_URL}/api/dashboard", headers=headers)
    initial_stats = dash_resp.json().get("stats", {})
    print(f"Initial Stats: {initial_stats}")
    initial_drafts = initial_stats.get("draft", 0)

    # 3. Manual Generation
    print("\n--- Test 3: Manual Generation of 2 Posts ---")
    gen_resp = requests.post(f"{BASE_URL}/api/generate", json={"count": 2}, headers=headers)
    if gen_resp.status_code != 200:
        print(f"FAIL: Generation trigger failed: {gen_resp.text}")
        sys.exit(1)
    
    poll_pipeline_idle()

    # Verify drafts increased
    dash_resp = requests.get(f"{BASE_URL}/api/dashboard", headers=headers)
    stats = dash_resp.json().get("stats", {})
    recent_posts = dash_resp.json().get("recent_posts", [])
    print(f"Current Stats: {stats}")
    
    drafts_after_gen = stats.get("draft", 0)
    if drafts_after_gen < initial_drafts + 2:
        print(f"FAIL: Draft count did not increase by 2. Expected >= {initial_drafts + 2}, got {drafts_after_gen}")
        sys.exit(1)
    print("PASS: Manual generation successful.")

    # Find the newly generated DRAFT post IDs
    draft_posts = [p for p in recent_posts if p.get("status") == "DRAFT"]
    if len(draft_posts) < 2:
        print("FAIL: Generated drafts not found in recent posts feed.")
        sys.exit(1)
    
    post_a_id = draft_posts[0]["id"]
    post_b_id = draft_posts[1]["id"]
    print(f"Selected Post A for Approval: {post_a_id}")
    print(f"Selected Post B for Rejection: {post_b_id}")

    # 4. Approve Workflow
    print("\n--- Test 4: Approve Post A ---")
    app_resp = requests.post(f"{BASE_URL}/api/posts/approve", json={"post_id": post_a_id}, headers=headers)
    if app_resp.status_code != 200:
        print(f"FAIL: Approve API failed: {app_resp.text}")
        sys.exit(1)
    
    # Verify post status is QUEUED
    verify_resp = requests.get(f"{BASE_URL}/api/posts/{post_a_id}", headers=headers)
    post_a = verify_resp.json()
    if post_a.get("status") != "QUEUED" or not post_a.get("approved_at") or post_a.get("approved_by") != "admin":
        print(f"FAIL: Post A states incorrect: {post_a}")
        sys.exit(1)
    
    # Verify publish_queue entry
    dash_resp = requests.get(f"{BASE_URL}/api/dashboard", headers=headers)
    queue = dash_resp.json().get("publishing_queue", [])
    if not any(q.get("post_id") == post_a_id for q in queue):
        print(f"FAIL: Post A not found in publishing queue feed: {queue}")
        sys.exit(1)
    print("PASS: Approve workflow verified.")

    # 5. Reject Workflow & Replacement Generation
    print("\n--- Test 5: Reject Post B with Automatic Replacement ---")
    stats_before_reject = dash_resp.json().get("stats", {})
    drafts_before_reject = stats_before_reject.get("draft", 0)

    rej_resp = requests.post(f"{BASE_URL}/api/posts/reject", json={"post_id": post_b_id}, headers=headers)
    if rej_resp.status_code != 200:
        print(f"FAIL: Reject API failed: {rej_resp.text}")
        sys.exit(1)
    
    # Wait for the replacement generation pipeline to finish
    poll_pipeline_idle()

    # Verify original post status is REJECTED
    verify_resp = requests.get(f"{BASE_URL}/api/posts/{post_b_id}", headers=headers)
    post_b = verify_resp.json()
    if post_b.get("status") != "REJECTED" or not post_b.get("rejected_at"):
        print(f"FAIL: Post B status not REJECTED: {post_b}")
        sys.exit(1)

    # Verify drafts count remained stable (B rejected: -1, replacement generated: +1)
    dash_resp = requests.get(f"{BASE_URL}/api/dashboard", headers=headers)
    stats_after_reject = dash_resp.json().get("stats", {})
    drafts_after_reject = stats_after_reject.get("draft", 0)
    print(f"Draft count before reject: {drafts_before_reject}, after reject/replacement: {drafts_after_reject}")
    if drafts_after_reject != drafts_before_reject:
        print(f"FAIL: Total draft posts count changed. Expected stability ({drafts_before_reject}), got {drafts_after_reject}")
        sys.exit(1)
    print("PASS: Reject and replacement workflow verified.")

    # 6. Publish Queue Worker Processing
    print("\n--- Test 6: Process Publishing Queue ---")
    pub_resp = requests.post(f"{BASE_URL}/api/posts/publish", headers=headers)
    if pub_resp.status_code != 200:
        print(f"FAIL: Publish API failed: {pub_resp.text}")
        sys.exit(1)
    
    # Verify post A status is PUBLISHED (or FAILED if mock failed, but mock returns success by default)
    verify_resp = requests.get(f"{BASE_URL}/api/posts/{post_a_id}", headers=headers)
    post_a_updated = verify_resp.json()
    print(f"Post A publishing state: {post_a_updated.get('status')}")
    if post_a_updated.get("status") != "PUBLISHED" or not post_a_updated.get("published_at"):
        print(f"FAIL: Post A not PUBLISHED: {post_a_updated}")
        sys.exit(1)
    
    # Check logs
    dash_resp = requests.get(f"{BASE_URL}/api/dashboard", headers=headers)
    activity = dash_resp.json().get("recent_activity", [])
    if not any(a.get("action") == "publish" and a.get("entity_id") == post_a_id for a in activity):
        print(f"FAIL: Publish activity log missing: {activity}")
        sys.exit(1)
    print("PASS: Publish queue worker processed successfully.")

    # 7. Vercel Cron Auto Generation
    print("\n--- Test 7: Vercel Cron Auto-Generation ---")
    cron_resp = requests.post(f"{BASE_URL}/api/cron/generate", headers=cron_headers)
    if cron_resp.status_code != 200:
        print(f"FAIL: Cron generate endpoint failed: {cron_resp.text}")
        sys.exit(1)
    
    poll_pipeline_idle()
    
    # Verify 4 drafts generated
    dash_resp = requests.get(f"{BASE_URL}/api/dashboard", headers=headers)
    history = dash_resp.json().get("generation_history", [])
    latest_run = history[0] if history else {}
    print(f"Latest run source: {latest_run.get('source')}, status: {latest_run.get('status')}, count: {latest_run.get('generated_count')}")
    if latest_run.get("source") != "AUTO" or latest_run.get("generated_count") != 4:
        print(f"FAIL: Cron run did not generate exactly 4 posts: {latest_run}")
        sys.exit(1)
    print("PASS: Vercel Cron generation successfully simulated.")

    # 8. Vercel Cron Cleanup
    print("\n--- Test 8: Vercel Cron Cleanup ---")
    cleanup_resp = requests.post(f"{BASE_URL}/api/cron/cleanup", headers=cron_headers)
    if cleanup_resp.status_code != 200:
        print(f"FAIL: Cron cleanup endpoint failed: {cleanup_resp.text}")
        sys.exit(1)
    print("PASS: Vercel Cron cleanup successfully executed.")

    print("\n====================================================")
    print("ALL END-TO-END INTEGRATION TESTS PASSED SUCCESSFULLY!")
    print("====================================================")

if __name__ == "__main__":
    run_tests()
