import requests
import re
from bs4 import BeautifulSoup

def spider(max_pages):
    page = 1
    while(page < max_pages):
        url = 'http://creativeworks.tistory.com/' + str(page)
        source_code = requests.get(url)
        plain_text = source_code.text
        soup = BeautifulSoup(plain_text, "lxml")
        for link in soup.select('div > h3'):
            title = re.compile('<h3 class="tit_post">(.+)</h3>', str(link))
            print(title)
        page += 1


spider(10)