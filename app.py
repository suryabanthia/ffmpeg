import os
import ffmpeg
import uuid
from flask import Flask, request, jsonify
from google.cloud import storage

app = Flask(__name__)

# Initialize the Google Cloud Storage client
# It will automatically use the credentials from the environment variable
storage_client = storage.Client()

# Get your destination bucket name from an environment variable for security
DESTINATION_BUCKET_NAME = os.environ.get('GCS_BUCKET_NAME')

def upload_to_gcs(local_path, bucket_name):
    """Helper function to upload a file to GCS and return its public URL."""
    destination_blob_name = os.path.basename(local_path)
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_filename(local_path)
    os.remove(local_path) # Clean up the temporary file from the Render server
    return blob.public_url

@app.route('/process', methods=['POST'])
def process_video():
    data = request.get_json()
    operation = data.get('operation')
    
    # --- OPERATION 1: EXTRACT AUDIO ---
    if operation == 'extract_audio':
        video_url = data.get('videoUrl')
        if not video_url:
            return jsonify({"error": "Missing 'videoUrl' for 'extract_audio' operation"}), 400
        
        local_audio_path = f"/tmp/{uuid.uuid4()}.mp3"
        
        try:
            (
                ffmpeg
                .input(video_url)
                .output(local_audio_path, vn=None, acodec='libmp3lame', ar=44100)
                .overwrite_output()
                .run()
            )
            public_audio_url = upload_to_gcs(local_audio_path, DESTINATION_BUCKET_NAME)
            return jsonify({"audioUrl": public_audio_url}), 200
        except Exception as e:
            return jsonify({"error": f"FFmpeg error: {str(e)}"}), 500

    # --- OPERATION 2: CREATE SPLIT-SCREEN CLIP ---
    elif operation == 'create_split_screen_clip':
        params = data.get('params', {})
        podcast_url = params.get('podcast_url')
        gameplay_url = params.get('gameplay_url')
        bgm_url = params.get('bgm_url')
        start_time = params.get('start_time')
        end_time = params.get('end_time')

        if not all([podcast_url, gameplay_url, start_time, end_time]):
            return jsonify({"error": "Missing parameters for 'create_split_screen_clip' operation"}), 400

        duration = float(end_time) - float(start_time)
        local_output_path = f"/tmp/{uuid.uuid4()}.mp4"

        try:
            # Define inputs
            podcast_input = ffmpeg.input(podcast_url, ss=start_time, t=duration)
            gameplay_input = ffmpeg.input(gameplay_url, ss=0, t=duration) # Start gameplay from the beginning
            
            # Scale and crop videos
            top_video = podcast_input.video.filter('scale', '1080', '-1').filter('crop', '1080', '960')
            bottom_video = gameplay_input.video.filter('scale', '1080', '-1').filter('crop', '1080', '960')
            
            # Stack videos vertically
            stacked_video = ffmpeg.filter([top_video, bottom_video], 'vstack')

            # Mix audio if BGM is provided
            if bgm_url:
                bgm_input = ffmpeg.input(bgm_url).audio.filter('aloop', loop=-1, size=2e9)
                final_audio = ffmpeg.filter([podcast_input.audio, bgm_input], 'amix', inputs=2, duration='first', dropout_transition=2)
                ffmpeg.output(stacked_video, final_audio, local_output_path, acodec='aac', vcodec='libx264').overwrite_output().run()
            else:
                # Use only podcast audio if no BGM
                ffmpeg.output(stacked_video, podcast_input.audio, local_output_path, acodec='aac', vcodec='libx264').overwrite_output().run()

            public_clip_url = upload_to_gcs(local_output_path, DESTINATION_BUCKET_NAME)
            return jsonify({"clipUrl": public_clip_url}), 200
            
        except Exception as e:
            return jsonify({"error": f"FFmpeg error: {str(e)}"}), 500

    else:
        return jsonify({"error": "Invalid or missing 'operation' specified"}), 400
