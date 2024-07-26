# Importing the necessary module and function
from simple_image_download import simple_image_download as simp 

# Creating a response object
response = simp.simple_image_download

## Keyword
keyword = "Dog"

# Downloading images
try:
    response().download(keyword, 20)
    print("Images downloaded successfully.")
except Exception as e:
    print("An error occurred:", e)