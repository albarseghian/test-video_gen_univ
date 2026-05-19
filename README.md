# AI Video & Test Generator

This project uses Flask, Gemini AI, and MoviePy to transform Word documents and PowerPoint slides into educational videos with accompanying evaluation tests.

## Features
- **Automated Voiceover:** Extracts "VO" tags from Word docs and generates high-quality audio using gTTS.
- **Slide Processing:** Converts PPTX slides to images and uses Gemini 1.5 Flash to provide "beautify" suggestions.
- **Video Assembly:** Synchronizes slides with generated audio segments into a final MP4 video.
- **AI Test Generation:** Creates a 10-question evaluation test based on the document content using Gemini 1.5 Pro.

## Setup
1. **Environment Variables:**
   Create a `.env` file and add your Gemini API Key:
   ```env
   GEMINI_API_KEY=your_actual_api_key_here
   ```

2. **Installation:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run with Docker:**
   ```bash
   docker build -t video-gen-app .
   docker run -p 5000:5000 --env-file .env video-gen-app
   ```

## Usage
Upload your `.docx` (with VO tags) and `.pptx` files via the web interface at `http://localhost:5000`.