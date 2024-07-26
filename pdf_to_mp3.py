import PyPDF2
import pyttsx3

# Open the PDF file (Enter Path To Your PDF)
file = open('story.pdf', 'rb')
readpdf = PyPDF2.PdfReader(file)

# Initialize text-to-speech engine
speaker = pyttsx3.init()
rate = speaker.getProperty('rate')   # Get current speaking rate
speaker.setProperty('rate', 200)

volume = speaker.getProperty('volume')
speaker.setProperty('volume', 1)  # Set volume level (0.0 to 1.0)

# Get and set a different voice
voices = speaker.getProperty('voices')
for voice in voices:
    if "english" in voice.name.lower() and "us" in voice.name.lower():
        speaker.setProperty('voice', voice.id)
        break
# Iterate over each page in the PDF
for pagenumber in range(len(readpdf.pages)):
    # Extract text from the page
    page = readpdf.pages[pagenumber]
    text = page.extract_text()
    
    # Use the speaker to read the text
    # speaker.say(text)
    # speaker.runAndWait()

# Save the last extracted text to an audio file (if needed)
speaker.save_to_file(text, 'story.mp3')
speaker.runAndWait()

# Stop the speaker
speaker.stop()

# Close the PDF file
file.close()