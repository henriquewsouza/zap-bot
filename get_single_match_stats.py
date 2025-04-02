from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time
import json

def fetch_match_stats_with_selenium(match_id):
    url = f"https://gamersclub.com.br/lobby/match/{match_id}/1"
    
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    # Optionally add more arguments to mimic a real browser
    chrome_options.add_argument("--window-size=1920,1080")
    
    driver = webdriver.Chrome(options=chrome_options)
    driver.get(url)
    
    # Wait for Cloudflare to process the challenge. Adjust sleep time if needed.
    time.sleep(10)
    
    # Get the page source once the challenge is solved
    page_source = driver.page_source
    driver.quit()
    
    try:
        data = json.loads(page_source)
    except Exception as e:
        print("Error decoding JSON from Selenium response:", e)
        return None
    
    local_filename = f"matches_{match_id}.json"
    with open(local_filename, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, indent=4))
    print(f"Saved stats for match {match_id} to local file: {local_filename}")
    return local_filename

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python get_single_match_stats_selenium.py <match_id>")
        sys.exit(1)
    match_id = sys.argv[1]
    fetch_match_stats_with_selenium(match_id)
