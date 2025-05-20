#!/usr/bin/env python
# coding: utf-8

import requests
import time
from bs4 import BeautifulSoup
from config import INCOMING, INSTAPAPER_USERNAME, INSTAPAPER_PASSWORD         

USERNAME = INSTAPAPER_USERNAME
PASSWORD = INSTAPAPER_PASSWORD

if not USERNAME or not PASSWORD:
    raise ValueError("Por favor, define las variables de entorno INSTAPAPER_USERNAME y INSTAPAPER_PASSWORD")

s = requests.Session()
s.post("https://www.instapaper.com/user/login", data={
    "username": USERNAME,
    "password": PASSWORD,
    "keep_logged_in": "yes"
})

base = INCOMING.as_posix() + "/" 

def get_ids(page=1):
    r = s.get("https://www.instapaper.com/u/" + str(page))
    print(r.url)
    soup = BeautifulSoup(r.text, "html.parser")

    articles = soup.find(id="article_list").find_all("article")
    ids = [i["id"].replace("article_", "") for i in articles]
    has_more = soup.find(class_="paginate_older") is not None
    return ids, has_more


def get_article(id):
    r = s.get("https://www.instapaper.com/read/" + str(id))
    soup = BeautifulSoup(r.text, "html.parser")

    title = soup.find(id="titlebar").find("h1").getText()
    origin = soup.find(id="titlebar").find(class_="origin_line")
    content = soup.find(id="story").decode_contents()
    return {
        "title": title.strip(),
        "origin": origin,
        "content": content.strip()
    }

# Function to truncate file name
def truncate_filename(name, extension, max_length=200):
    total_length = len(name) + len(extension) + 1 # +1 for the dot in ".html"
    if total_length > max_length:
        name = name[:max_length - len(extension) - 1]  # Truncate the excess
    return name + extension


def download_article(id):
    article = get_article(id)
    file_name = article["title"]
    file_name = "".join([c for c in file_name if c.isalpha()
                         or c.isdigit() or c == " "]).rstrip()
    
    file_name = base + truncate_filename(file_name, ".html")
    print(file_name)

    with open(file_name, "w") as file:
        file.write("<!DOCTYPE html>\n<html>\n<head>\n<meta charset=\"UTF-8\">\n")
        file.write("<title>%s</title>" % (article["title"]))
        file.write("</head>\n<body>")
        file.write("<h1>%s</h1>" % (article["title"]))
        file.write("<div id='origin'>%s · %s</div>" % (article["origin"], id))
        file.write(article["content"])
        file.write("</body>\n</html>")
    return file_name


has_more = True
page = 1

failure_log = open("failed.txt", "a+")

while has_more:
    print("Page " + str(page))
    ids, has_more = get_ids(page)
    for id in ids:
        print("  " + id + ": ", end="")
        start = time.time()
        try:
            file_name = download_article(id)
        except Exception as e:
            print(f"failed!")
            print(e)
            failure_log.write("%s\t%s\n" % (id, str(e)))
            failure_log.flush()
        else:
            duration = time.time() - start
            print(str(round(duration, 2)) + " seconds")
    page += 1
