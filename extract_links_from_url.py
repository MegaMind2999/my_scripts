import requests
from bs4 import BeautifulSoup
import argparse

def extract_links(url):
    try:
        # Fetch the webpage content
        response = requests.get("http://"+url)
        response.raise_for_status()  # Check for HTTP errors
        
        # Parse the HTML content
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract all links
        links = [a_tag['href'] for a_tag in soup.find_all('a', href=True)]
        return links
    
    except requests.exceptions.RequestException as e:
        print(f"Error fetching {url}: {e}")
        return []

def main():
    parser = argparse.ArgumentParser(description="Extract all links from a given URL")
    parser.add_argument("url", help="The URL of the webpage to extract links from")
    args = parser.parse_args()
    
    url = args.url
    all_links = extract_links(url)
    for link in all_links:
        print("wget "+url+"/"+link)

if __name__ == "__main__":
    main()