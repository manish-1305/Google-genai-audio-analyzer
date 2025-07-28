from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, send_file, send_from_directory, flash
from werkzeug.utils import secure_filename
import uuid

from google.cloud import texttospeech_v1
import google.generativeai as genai
import io
import os

credential_path = r"service_account.json"
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credential_path

app = Flask(__name__)
app.secret_key = '11477asdf'

genai.configure(api_key="AIzaSyDdDWRjpOXDiPT7BsRbV2dXpmEyppIR6Sk")

client = texttospeech_v1.TextToSpeechClient()
client2 = speech.SpeechClient()

# Configure upload folder
UPLOAD_FOLDER = '/tmp/uploads'
TTS_FOLDER = '/tmp/tts'

# Ensure the directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TTS_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {'wav'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['TTS_FOLDER'] = TTS_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_files(folder):
    files = [f for f in os.listdir(folder) if allowed_file(f)]
    files.sort(reverse=True)
    return files

@app.route('/')
def index():
    files = get_files(app.config['UPLOAD_FOLDER'])
    tts_files = get_files(app.config['TTS_FOLDER'])
    return render_template('index.html', files=files, tts_files=tts_files)


def upload_to_gemini(path, mime_type="audio/wav"):
    """Uploads the given file to Gemini."""
    file = genai.upload_file(path, mime_type=mime_type)
    print(f"Uploaded file '{file.display_name}' as: {file.uri}")
    return file

# Configure the model
generation_config = {
    "temperature": 1,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 8192,
    "response_mime_type": "text/plain",
}

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    generation_config=generation_config,
)

def transcribe_and_analyze_with_gemini(file_path):
    file = upload_to_gemini(file_path)
    
    # Start a new chat session with the model
    chat_session = model.start_chat(
        history=[
            {
                "role": "user",
                "parts": [
                    file,
                    "transcribe the audio and perform sentiment analysis and display sentiment of the text. response format: the audio says " ", its sentiment is "".",
                ],
            },
        ]
    )
    
    # Send message to get response
    response = chat_session.send_message("transcribe the audio and perform sentiment analysis")
    
    
    return response.text

def sample_synthesize_speech(text=None, ssml=None):
    input = texttospeech_v1.SynthesisInput()
    if ssml:
      input.ssml = ssml
    else:
      input.text = text

    voice = texttospeech_v1.VoiceSelectionParams()
    voice.language_code = "en-US"
    # voice.ssml_gender = "MALE"

    audio_config = texttospeech_v1.AudioConfig()
    audio_config.audio_encoding = "LINEAR16"

    request = texttospeech_v1.SynthesizeSpeechRequest(
        input=input,
        voice=voice,
        audio_config=audio_config,
    )

    response = client.synthesize_speech(request=request)

    return response.audio_content    

@app.route('/upload', methods=['POST'])
def upload_audio():
    if 'audio_data' not in request.files:
        flash('No audio data')
        return redirect(request.url)

    file = request.files['audio_data']
    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)

    if file:
        # Save the uploaded audio file
        filename = datetime.now().strftime("%Y%m%d-%I%M%S%p") + '.wav'
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        # Call the transcribe and sentiment analysis function using Gemini API
        transcript = transcribe_and_analyze_with_gemini(file_path)

        # Save the transcript and sentiment to a .txt file
        txt_filename = filename.replace('.wav', '-tts.txt')
        txt_file_path = os.path.join(app.config['TTS_FOLDER'], txt_filename)
        with open(txt_file_path, 'w') as txt_file:
            txt_file.write(f"{transcript}")

        # Generate TTS audio from the transcript and sentiment
        file_content = f"{transcript}"
        audio_content = sample_synthesize_speech(text=file_content)

        # Save the synthesized TTS audio
        tts_filename = filename.replace('.wav', '-tts.wav')
        tts_file_path = os.path.join(app.config['TTS_FOLDER'], tts_filename)
        with open(tts_file_path, 'wb') as tts_file:
            tts_file.write(audio_content)

        flash(f'Transcript and sentiment analysis saved as {txt_filename}')

    return redirect('/')



@app.route('/tts/<filename>')
def uploaded_tts_file(filename):
    return send_from_directory(app.config['TTS_FOLDER'], filename)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/script.js',methods=['GET'])
def scripts_js():
    return send_file('./script.js')

if __name__ == '__main__':
    app.run(debug=True, port=8080)