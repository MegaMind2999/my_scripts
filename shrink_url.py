import pyshorteners
def generate_short_url(long_url):
  s = pyshorteners.Shortener()
  return s.tinyurl.short(long_url)

long_url = input('Paste Long URl \n')
short_url = generate_short_url(long_url)
print(short_url)