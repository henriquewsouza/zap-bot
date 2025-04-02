import undetected_chromedriver as uc
import time
import json
import os

def fetch_match_stats_with_uc(match_id):
    url = f"https://gamersclub.com.br/lobby/match/{match_id}/1"
    
    options = uc.ChromeOptions()
    options.headless = True  # Set to False for debugging
    options.add_argument("--window-size=1920,1080")
    
    driver = uc.Chrome(options=options)
    driver.get(url)
    
    # Wait for Cloudflare challenge to be processed (adjust as needed)
    time.sleep(10)
    
    page_source = driver.page_source
    driver.quit()
    
    try:
        data = json.loads(page_source)
        print("Successfully loaded JSON data!")
    except Exception as e:
        print("Error decoding JSON from undetected_chromedriver response:", e)
        print("Page source (first 500 chars):", page_source[:500])
        return None

    # Ensure the matches folder exists
    os.makedirs("matches", exist_ok=True)
    local_filename = os.path.join("matches", f"{match_id}.json")
    with open(local_filename, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, indent=4))
    print(f"Saved stats for match {match_id} to local file: {local_filename}")
    return local_filename

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python get_single_match_stats.py <match_id>")
        sys.exit(1)
    match_id = sys.argv[1]
    fetch_match_stats_with_uc(match_id)
