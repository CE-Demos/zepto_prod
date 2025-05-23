# video_gen.py
import os
import cv2
import requests
import json
import time
from datetime import timedelta
import subprocess
import shutil
import uuid
import base64
from google import genai
import requests
from google.genai import types
from google.genai.types import GenerateVideosConfig, Image
from google.cloud import storage
from google.auth.transport.requests import Request
from google.auth import default as google_auth_default
from vertexai.generative_models import GenerativeModel, Image
from moviepy.editor import VideoFileClip, concatenate_videoclips, vfx
from PIL import Image, ImageOps
from rembg import remove
import io

# --- Google Cloud Configuration ---
GCS_BUCKET_NAME = "veo_exps_prod"  

# --- Vertex AI Configuration ---
PROJECT_ID = "veo-testing" 
LOCATION = "us-central1"  

IMAGEN3_MODEL_NAME = "imagen-3.0-capability-001" 
VEO2_MODEL_NAME = "veo-2.0-generate-exp"
VEO2_API_ENDPOINT_ID = "https://us-central1-aiplatform.googleapis.com/v1/projects/veo-testing/locations/us-central1/publishers/google/models/veo-2.0-generate-exp:predictLongRunning" 
# VEO2_INTERPOLATION_PROMPT = "Make the model WALK towards the camera and show the garments from different angles."
#VEO2_INTERPOLATION_PROMPT = "A video with smooth transition from the first frame to the last frame."
# VEO2_INTERPOLATION_PROMPT = "A realistic transition, showcasing the apparel with the confident, professional walk of a brand ambassador, optimized for e-commerce product presentation"
VEO2_INTERPOLATION_PROMPT = "[Camera: Medium wide shot, slowly dollying in towards the model to emphasize presence][Lighting: Slightly more dramatic, emphasizing shadows and highlights for depth][Style: Majestic, confident, aspirational] Brand ambassador walking to showcase e-commerce product in e-commerce website catalog. Don't change the product style."
VEO2_EXTENSION_PROMPT = "Continue the video with seamless motions."
VEO2_EXTENSION_DURATION_SECONDS = 5 


# Confirguration for Advanced Veo2 editing features
URL_PREFIX = f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/{LOCATION}/publishers/google/models/{VEO2_MODEL_NAME}"
OPERATION_URL_PREFIX = f"projects/{PROJECT_ID}/locations/{LOCATION}/publishers/google/models/{VEO2_MODEL_NAME}/operations"
generate_url = f"{URL_PREFIX}:predictLongRunning"
retrieve_url = f"{URL_PREFIX}:fetchPredictOperation"


TEMP_DOWNLOAD_SUBDIR = "temp_gcs_downloads"

# --- Helper Functions (GCS Upload - largely unchanged) ---
def upload_to_gcs(bucket_name, source_path, destination_blob_name):
    """Uploads a file to the GCS bucket."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    if not bucket.exists():
        print(f"Bucket {bucket_name} does not exist. Please create it or check the name.")
        return False
    
    blob = bucket.blob(destination_blob_name)
    try:
        blob.upload_from_filename(source_path)
        print(f"Uploaded {source_path} to gs://{bucket_name}/{destination_blob_name}")
        return True
    except Exception as e:
        print(f"Error uploading {source_path} to {destination_blob_name}: {e}")
        return False
    

def download_blob(bucket_name: str, source_blob_name: str, destination_file_name: str):
    """Downloads a blob from a GCS bucket."""
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(source_blob_name)
        print(f"Attempting to download gs://{bucket_name}/{source_blob_name} to {destination_file_name}...")
        blob.download_to_filename(destination_file_name)
        print(f"Blob downloaded successfully.")
    except Exception as e:
        raise ConnectionError(f"Failed to download blob gs://{bucket_name}/{source_blob_name}: {e}")


# Attempt to import Vertex AI SDK. Provide guidance if not found.
try:
    from vertexai.preview.vision_models import Image as VertexImage, ImageGenerationModel
    # Note: As of late 2023/early 2024, ImageEditingModel was in preview.
    # The exact class might be ImageGenerationModel with editing parameters,
    # or a dedicated ImageEditingModel. Please check the latest Vertex AI SDK documentation.
    # For this example, we'll structure it based on common patterns for such models.
except ImportError:
    print("Vertex AI SDK not found or model classes have changed. Please install/update:")
    print("pip install google-cloud-aiplatform --upgrade")
    print("And check the latest Vertex AI SDK documentation for Image Editing models.")
    VertexImage = None
    ImageGenerationModel = None


# --- Helper Functions (GCS, Veo Sim - largely unchanged) ---


def get_auth_headers() -> dict:
    """
    Authenticates with Google Cloud and returns authorization headers.
    Uses default credentials (e.g., GOOGLE_APPLICATION_CREDENTIALS, gcloud login, or VM service account).
    """
    credentials, project_id = google_auth_default()
    credentials.refresh(Request()) # Ensure credentials are fresh
    return {"Authorization": f"Bearer {credentials.token}", "Content-Type": "application/json"}

def upload_to_gcs(bucket_name, source_path, destination_blob_prefix, is_folder=False):
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    if not bucket.exists():
        print(f"Bucket {bucket_name} does not exist. Please create it or check the name.")
        return False
    # (Rest of the GCS upload logic from previous version)
    if is_folder:
        for dirpath, _, filenames in os.walk(source_path):
            for filename in filenames:
                local_path = os.path.join(dirpath, filename)
                relative_path = os.path.relpath(local_path, source_path)
                blob_name = os.path.join(destination_blob_prefix, relative_path)
                blob = bucket.blob(blob_name)
                try:
                    blob.upload_from_filename(local_path)
                    # print(f"Uploaded {local_path} to gs://{bucket_name}/{blob_name}")
                except Exception as e:
                    print(f"Error uploading {local_path}: {e}")
        return True
    else:
        filename = os.path.basename(source_path)
        blob_name = os.path.join(destination_blob_prefix, filename)
        blob = bucket.blob(blob_name)
        try:
            blob.upload_from_filename(source_path)
            # print(f"Uploaded {source_path} to gs://{bucket_name}/{blob_name}")
            return True
        except Exception as e:
            print(f"Error uploading {source_path}: {e}")
            return False
    return True

def upload_final_video_to_gcs(bucket_name, source_path, destination_blob_name):
    # ... (no change from previous version)
    storage_client = storage.Client(project=PROJECT_ID if PROJECT_ID != "veo-testing" else None)
    bucket = storage_client.bucket(bucket_name)
    if not bucket.exists(): print(f"Bucket {bucket_name} does not exist."); return False
    blob = bucket.blob(destination_blob_name)
    try:
        blob.upload_from_filename(source_path)
        print(f"Uploaded {source_path} to gs://{bucket_name}/{destination_blob_name}")
        return True
    except Exception as e: print(f"Error uploading {source_path} to {destination_blob_name}: {e}"); return False


# def generate_signed_url(bucket_name: str, blob_name: str, expiration_seconds: int = 3600) -> str | None:
#     """Generates a signed URL for a GCS blob."""
#     try:
#         storage_client = storage.Client(project=PROJECT_ID if PROJECT_ID != "veo-testing" else None)
#         bucket = storage_client.bucket(bucket_name)
#         blob = bucket.blob(blob_name)

#         # Generate the signed URL
#         # Note: This requires credentials with the 'storage.objects.get' permission
#         # and potentially 'iam.serviceAccounts.signBlob' if using a service account
#         # without direct key file access (e.g., default VM service account).
#         signed_url = blob.generate_signed_url(
#             expiration=timedelta(seconds=expiration_seconds),
#             method='GET'
#         )
#         print(f"Generated signed URL for gs://{bucket_name}/{blob_name}")
#         return signed_url
#     except Exception as e:
#         print(f"Error generating signed URL for gs://{bucket_name}/{blob_name}: {e}")
#         return None


# def imagen3_replace_background(product_image_path: str, background_image_path: str, output_image_path: str) -> bytes | None:
   
#     """
#     Placeholder for Imagen3 API call to replace the background of a product image
#     with a new background image. This is an IMAGE EDITING or COMPOSITING task.

#     Args:
#         product_image_bytes: Bytes of the product image (foreground).
#         background_image_bytes: Bytes of the new background image.
#         project_id: Your Google Cloud Project ID.
#         location: The GCP region where your Imagen model/endpoint is.
#     Returns:
#         Bytes of the product image with the new background, or None if failed.
#     """
#     print(f"INFO: Calling Imagen3 (model for image editing/compositing) "
#         f"to replace background for images.")

#     try:
#         with open(product_image_path, "rb") as f:
#             product_image_bytes_content = f.read()
#         with open(background_image_path, "rb") as f:
#             background_image_bytes_content = f.read()
#     except Exception as e:
#         print(f"  ERROR: Failed to read local image files to bytes: {e}")
#         return None
       
    
#     try:
#         client = genai.Client(api_key='AIzaSyCwtqZvVOiEx86-ZY1Xssn1sw6sikVLia0')

#         from vertexai.preview.vision_models import (
#             Image,
#             ImageGenerationModel,
#             ControlReferenceImage,
#             StyleReferenceImage,
#             SubjectReferenceImage,
#             RawReferenceImage,
#         )

#         generation_model = ImageGenerationModel.from_pretrained("imagen-3.0-capability-001")

#         reference_images = [
#             SubjectReferenceImage(
#                 reference_id=1,
#                 image=product_image_bytes_content,  
#                 subject_type="SUBJECT_TYPE_PERSON",
#             ),  
#             SubjectReferenceImage(
#                 reference_id=2,
#                 image=background_image_bytes_content,  
#                 subject_description="",        
#                 subject_type="SUBJECT_TYPE_DEFAULT",
#             ),  
#         ]

#         response = generation_model._generate_images(
#             prompt="Add image [2] as background for image [1].",
#             number_of_images=1,
#             negative_prompt="",
#             aspect_ratio="9:16",
#             person_generation="allow_adult",
#             safety_filter_level="block_few",
#             reference_images=reference_images,
#         )

#         if not response: # 
#             print("ERROR: Imagen3 API returned an empty response.")
#             return None
        
#         generated_image_object = response[0]
#         processed_image_bytes_result = None
#         if hasattr(generated_image_object, 'image_bytes'):
#                 processed_image_bytes_result = generated_image_object.image_bytes
#         elif hasattr(generated_image_object, '_image_bytes'):
#                 processed_image_bytes_result = generated_image_object._image_bytes

#         if processed_image_bytes_result:
#                 print(f"  INFO: Successfully extracted {len(processed_image_bytes_result)} bytes from Imagen 3 response.")
#                 # **CRUCIAL STEP: Save the bytes to the output file**
#                 with open(output_image_path, "wb") as f_out:
#                     f_out.write(processed_image_bytes_result)
#                 print(f"  Imagen 3 processed image saved locally to {output_image_path}")
#                 return output_image_path # **Return the string path**
#         else:
#                 print(f"  ERROR: Could not find image bytes attribute on the Imagen 3 response object.")
#                 # Attempt fallback simulation if bytes not found in response
#                 return run_imagen3_fallback_simulation(product_image_path, background_image_path, output_image_path, "No image bytes in API response")

#     except Exception as e:
#             print(f"  ERROR: Imagen 3 API call for background replacement failed: {e}")
#             # Attempt fallback simulation on any API call error
#             return run_imagen3_fallback_simulation(product_image_path, background_image_path, output_image_path, f"API call exception: {e}")


# def run_imagen3_fallback_simulation(product_image_path, background_image_path, output_image_path, reason=""):
#     """Helper function for the rembg+PIL fallback simulation."""
#     print(f"  Executing rembg+PIL fallback simulation for Imagen 3. Reason: {reason}")
#     try:
#         with open(product_image_path, 'rb') as i_file: product_image_bytes_content = i_file.read()
#         with open(background_image_path, 'rb') as f: background_image_bytes_content = f.read()
        
#         prod_fg_bytes = remove(product_image_bytes_content)
#         product_foreground_rgba = Image.open(io.BytesIO(prod_fg_bytes)).convert("RGBA")
#         background_img_rgba = Image.open(io.BytesIO(background_image_bytes_content)).convert("RGBA")
        
#         if background_img_rgba.size != product_foreground_rgba.size:
#             background_img_rgba = background_img_rgba.resize(product_foreground_rgba.size, Image.LANCZOS)
        
#         final_image = Image.alpha_composite(background_img_rgba, product_foreground_rgba)
#         final_image.save(output_image_path)
#         print(f"  SIMULATED (rembg+PIL) Imagen 3 output saved to {output_image_path}")
#         return output_image_path
#     except Exception as e_sim:
#         print(f"  ERROR: rembg+PIL simulation failed: {e_sim}")
#         return None

def interpolate_video_veo2(
    start_image_path: str,
    end_image_path: str,
    prompt_text: str,
    output_local_video_path: str
) -> str | None:
    """
    Calls the Veo2 API to generate a video using interpolation from two frames.
    This function handles the long-running operation and returns the final API response.
    """
    print(f"Performing Veo 2 Interpolation: from '{os.path.basename(start_image_path)}' "
          f"to '{os.path.basename(end_image_path)}'")
    
    
    try:
        with open(start_image_path, "rb") as f:
            start_frame_bytes = f.read()
        start_frame_base64 = base64.b64encode(start_frame_bytes).decode('utf-8')

        with open(end_image_path, "rb") as f:
            end_frame_bytes = f.read()
        end_frame_base64 = base64.b64encode(end_frame_bytes).decode('utf-8')
    
    
    except Exception as e:
        print(f"  ERROR: Failed to read and encode local image files to base64: {e}")
        return None
    
    target_output_video_gcs_uri = f"gs://{GCS_BUCKET_NAME}/{output_local_video_path}"

    api_url = f"https://us-central1-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/us-central1/publishers/google/models/veo-2.0-generate-exp:predictLongRunning" 
    headers = get_auth_headers()

    headers['Content-Type'] = 'application/json'
    headers['charset'] = 'utf-8'

    new_url = f"https://us-central1-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/us-central1/publishers/google/models/veo-2.0-generate-exp:fetchPredictOperation"
    api_call_attempted = True

    
    
    request_body = {
        "instances": [{
            "prompt": prompt_text,
            "image": {"bytesBase64Encoded": start_frame_base64, "mimeType": "image/png"}, # Using 'content' for base64
            "lastFrame": {"bytesBase64Encoded": end_frame_base64, "mimeType": "image/png"} # Using 'content'
        }],
        "parameters": {
            "aspectRatio": "9:16",
            "durationSeconds": 8,
            "sampleCount" : 1,
            "storageUri": target_output_video_gcs_uri,
        }
    }
    
    os.makedirs(os.path.dirname(output_local_video_path), exist_ok=True)


    try:
        response = requests.post(api_url, headers=headers, data=json.dumps(request_body))
        response.raise_for_status() 
        
        operation_details = response.json()
        op_name = operation_details.get('name', 'N/A')

        print(f"API Response: {operation_details}")
        print(f"  SUCCESS (LRO Initiated): Veo 2 API call successful. Operation: {op_name}")

        max_iterations = 600
        interval_sec = 10

        new_request_body = {
            "operationName": op_name,
        }


        for i in range(max_iterations):
            try:
                polling_response = requests.post(new_url, headers=headers, data=json.dumps(new_request_body))
                polling_response.raise_for_status()

                print(f" Reponse from polling: {polling_response.text}")

                if '"done": true' in polling_response.text:
                    print(f" Reponse from polling: {polling_response.text}")
                    generated_videos = (
                        polling_response.json()["response"]["videos"]
                    )

                    print(f"The generated video samples are: {generated_videos}")

                    generated_videos_uri = (
                        polling_response.json()["response"]["videos"][0].get("gcsUri")
                    )
                    
                    return generated_videos_uri
            except requests.exceptions.RequestException as e:
                print(f"Polling failed for operation {op_name}: {e}")
                break  # Exit polling loop on error.
            except KeyError as e:
                print(f"KeyError during polling for {op_name}: {e}. polling_response: {polling_response.text}")
                break
            except Exception as e:
                print(f"An unexpected error occurred during polling: {e}")
                break

        print(f"Polling operation {op_name}, iteration {i+1}. Retrying in {interval_sec} seconds...")
        time.sleep(interval_sec)

    except requests.exceptions.HTTPError as e:
        print(f"  ERROR: HTTP Error during Veo 2 API call (with bytes): {e.response.status_code} - {e.response.text}")
        print(f"           This may indicate the API does not support byte content for images, expecting gcsUri.")
    except requests.exceptions.RequestException as e:
        print(f"  ERROR: Network or other Request Error during Veo 2 API call (with bytes): {e}")
    except Exception as e:
        print(f"  ERROR: An unexpected error occurred during Veo 2 API call (with bytes): {e}")
    
    return generated_videos_uri


def extend_video_veo2(
    input_video_path: str,
    prompt_text: str,
    output_video_path: str,
    # model_name: str # For actual API call
):
    """
    Calls the Veo2 API to extend an existing video.
    Assumes the API takes a 'video' input and 'extension_params'.
    """

    print(f"Performing Veo 2 Extension for: '{os.path.basename(input_video_path)}' with prompt: '{prompt_text}'")
    
    api_url = f"https://us-central1-aiplatform.googleapis.com/v1beta1/projects/{PROJECT_ID}/locations/us-central1/publishers/google/models/veo-2.0-generate-exp:predictLongRunning" 
    headers = get_auth_headers()
    headers['Content-Type'] = 'application/json'

    new_url = f"https://us-central1-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/us-central1/publishers/google/models/veo-2.0-generate-exp:fetchPredictOperation"

    target_output_video_gcs_uri = f"gs://{GCS_BUCKET_NAME}/{output_video_path}"

    request_body = {
        "instances": [
            {
                "prompt": prompt_text,
                "video": {
                    "gcsUri": input_video_path,
                    "mimeType": "video/mp4",
                }
            }
        ],
        "parameters": {
            "aspectRatio": "9:16", 
            "durationSeconds": 5, 
            "storageUri": target_output_video_gcs_uri
        }
    }

    try:
        response = requests.post(api_url, headers=headers, data=json.dumps(request_body))
        response.raise_for_status() 
        
        operation_details = response.json()
        op_name = operation_details.get('name', 'N/A')

        print(f"API Response: {operation_details}")
        print(f"  SUCCESS (LRO Initiated): Veo 2 API call successful. Operation: {op_name}")

        max_iterations = 600
        interval_sec = 10

        new_request_body = {
            "operationName": op_name,
        }


        for i in range(max_iterations):
            try:
                polling_response = requests.post(new_url, headers=headers, data=json.dumps(new_request_body))
                polling_response.raise_for_status()

                print(f" Reponse from polling: {polling_response.text}")

                if '"done": true' in polling_response.text:
                    print(f" Reponse from polling: {polling_response.text}")
                    generated_videos = (
                        polling_response.json()["response"]["videos"]
                    )

                    print(f"The generated video samples are: {generated_videos}")

                    generated_videos_uri = (
                        polling_response.json()["response"]["videos"][0].get("gcsUri")
                    )
                    
                    return generated_videos_uri
            except requests.exceptions.RequestException as e:
                print(f"Polling failed for operation {op_name}: {e}")
                break  # Exit polling loop on error.
            except KeyError as e:
                print(f"KeyError during polling for {op_name}: {e}. polling_response: {polling_response.text}")
                break
            except Exception as e:
                print(f"An unexpected error occurred during polling: {e}")
                break

        print(f"Polling operation {op_name}, iteration {i+1}. Retrying in {interval_sec} seconds...")
        time.sleep(interval_sec)

    except requests.exceptions.HTTPError as e:
        print(f"  ERROR: HTTP Error during Veo 2 API call (with bytes): {e.response.status_code} - {e.response.text}")
        print(f"           This may indicate the API does not support byte content for images, expecting gcsUri.")
    except requests.exceptions.RequestException as e:
        print(f"  ERROR: Network or other Request Error during Veo 2 API call (with bytes): {e}")
    except Exception as e:
        print(f"  ERROR: An unexpected error occurred during Veo 2 API call (with bytes): {e}")
    
    return generated_videos_uri
      

def alter_video_speed( # Renamed to avoid confusion if a real one is added
    input_video_path: str,
    output_video_path: str,
    speed_factor: float,
    run_temp_dir: str
):
    """
    Alters the playback speed of a video.
    The input_video_path can be a local path or a GCS URI.
    If GCS URI, it's downloaded first.
    """
    print(f"Altering speed for: '{os.path.basename(input_video_path)}' by factor {speed_factor:.2f}")
    
    local_input_path_for_processing = input_video_path
    is_gcs_input = input_video_path.startswith("gs://")
    temp_download_path = None

    if is_gcs_input:
        try:
            bucket_name_in, blob_name_in = input_video_path[5:].split("/", 1)
            temp_download_dir_specific = os.path.join(run_temp_dir, TEMP_DOWNLOAD_SUBDIR, "speed_alter_downloads")
            os.makedirs(temp_download_dir_specific, exist_ok=True)
            temp_download_path = os.path.join(temp_download_dir_specific, os.path.basename(blob_name_in))
            
            print(f"  Input is GCS URI. Downloading {input_video_path} to {temp_download_path}...")
            download_blob(bucket_name_in, blob_name_in, temp_download_path)
            local_input_path_for_processing = temp_download_path
        except Exception as e:
            print(f"  ERROR: Failed to download GCS video {input_video_path} for speed alteration: {e}")
            return None
    
    if not os.path.exists(local_input_path_for_processing):
        print(f"  ERROR: Input video for speed alteration not found at {local_input_path_for_processing}")
        return None

    if abs(speed_factor - 1.0) < 1e-5: # If speed factor is effectively 1.0
        print(f"  Speed factor is {speed_factor}, copying original video.")
        shutil.copy(local_input_path_for_processing, output_video_path)
        return output_video_path
    
    clip = None
    final_clip_processed = None
    try:
        print(f"  Processing video {local_input_path_for_processing} with moviepy...")
        clip = VideoFileClip(local_input_path_for_processing)
        final_clip_processed = clip.fx(vfx.speedx, speed_factor)
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_video_path), exist_ok=True)
        final_clip_processed.write_videofile(output_video_path, codec="libx264", audio_codec="aac", logger=None) # Added logger=None for less verbose output
        print(f"  Speed altered video saved to {output_video_path}")
        return output_video_path
    except Exception as e:
        print(f"  ERROR: MoviePy speed alteration for {os.path.basename(local_input_path_for_processing)} failed: {e}")
        return None


def concatenate_videos(video_paths_list: list, output_concatenated_video_path: str, run_temp_dir: str):
    """
    Concatenates multiple video files.
    Items in video_paths_list can be local paths or GCS URIs.
    GCS URIs are downloaded first.
    """
    print(f"Concatenating {len(video_paths_list)} videos into '{os.path.basename(output_concatenated_video_path)}'")
    
    if not video_paths_list:
        print("No videos to concatenate.")
        return None
    
    local_clips_for_concatenation = []
    downloaded_temp_files_for_cleanup = []

    temp_download_dir_specific = os.path.join(run_temp_dir, TEMP_DOWNLOAD_SUBDIR, "concat_downloads")
    os.makedirs(temp_download_dir_specific, exist_ok=True)

    try:
        for i, video_path_item in enumerate(video_paths_list):
            local_input_path_for_clip = video_path_item
            is_gcs_item = video_path_item.startswith("gs://")

            if is_gcs_item:
                try:
                    bucket_name_in, blob_name_in = video_path_item[5:].split("/", 1)
                    temp_download_path_item = os.path.join(temp_download_dir_specific, f"segment_{i}_{os.path.basename(blob_name_in)}")
                    print(f"  Segment {i+1} is GCS URI. Downloading {video_path_item} to {temp_download_path_item}...")
                    download_blob(bucket_name_in, blob_name_in, temp_download_path_item)
                    local_input_path_for_clip = temp_download_path_item
                    # downloaded_temp_files_for_cleanup.append(local_input_path_for_clip) # Cleanup handled by run_temp_dir
                except Exception as e:
                    print(f"  WARNING: Failed to download GCS video segment {video_path_item}: {e}. Skipping.")
                    continue
            if not os.path.exists(local_input_path_for_clip):
                print(f"  WARNING: Video segment file not found: {local_input_path_for_clip}. Skipping.")
                continue
            
            try:
                print(f"  Loading segment {i+1}: {os.path.basename(local_input_path_for_clip)}")
                clip = VideoFileClip(local_input_path_for_clip)
                local_clips_for_concatenation.append(clip)
            except Exception as e:
                print(f"  WARNING: Failed to load video segment {local_input_path_for_clip} with moviepy: {e}. Skipping.")

        if not local_clips_for_concatenation:
            print("  No valid video segments to concatenate after downloads/loading.")
            return None
        print(f"  Concatenating {len(local_clips_for_concatenation)} loaded clips with moviepy...")
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_concatenated_video_path), exist_ok=True)
        final_concatenated_clip = concatenate_videoclips(local_clips_for_concatenation, method="compose") # Use "compose" for overlapping audio/video
        final_concatenated_clip.write_videofile(output_concatenated_video_path, codec="libx264", audio_codec="aac", logger=None)
        final_concatenated_clip.close()
        print(f"  Concatenated video saved to {output_concatenated_video_path}")
        return output_concatenated_video_path
    except Exception as e:
        print(f"  ERROR: MoviePy video concatenation failed: {e}")
        return None
    finally:
        for clip_obj in local_clips_for_concatenation:
            clip_obj.close()


# --- Main Pipeline Function ---
def process_images_and_generate_videos_pipeline(
    product_images_temp_paths,
   # user_background_image_temp_path: str,
    playback_speed: float = 1.0
):
    run_id = str(uuid.uuid4())
    status_messages = [f"Pipeline Run ID: {run_id}"]
    
    base_temp_dir = "temp_processing_space"
    run_temp_dir = os.path.join(base_temp_dir, run_id)



    try: # Wrap main processing in a try block
        dir_paths = {
            "original_products": os.path.join(run_temp_dir, "0_original_products"),
            # "user_background": os.path.join(run_temp_dir, "1_user_background"),
            # "bg_added_products": os.path.join(run_temp_dir, "2_bg_added_products"),
            "interpolated_videos_local": os.path.join(run_temp_dir, "3_interpolated_videos_local"),
            "extended_videos_local": os.path.join(run_temp_dir, "4_extended_videos_local"),
            "concatenated_video_temp": os.path.join(run_temp_dir, "5_concatenated_video_temp"),
            "final_output": os.path.join(run_temp_dir, "6_final_output")
        }
        for path_key in dir_paths: # Use keys to iterate, more robust
            os.makedirs(dir_paths[path_key], exist_ok=True)
        status_messages.append(f"Temporary directories created under {run_temp_dir}")

        # 1. Prepare Inputs
        # bg_input_filename = os.path.basename(user_background_image_temp_path)
        # local_user_bg_path = os.path.join(dir_paths["user_background"], bg_input_filename)
        # shutil.copy(user_background_image_temp_path, local_user_bg_path)
        # status_messages.append(f"User background image '{bg_input_filename}' copied locally.")
        
        local_product_image_paths = {}
        for temp_file_obj in product_images_temp_paths:
            src_path = temp_file_obj.name; filename = os.path.basename(src_path)
            dst_path = os.path.join(dir_paths["original_products"], filename)
            shutil.copy(src_path, dst_path); local_product_image_paths[filename] = dst_path
        status_messages.append(f"Copied {len(local_product_image_paths)} product images locally.")

        # # 2. Replace Background (Imagen 3)
        # bg_added_image_paths = {} 
        # status_messages.append(f"\nStep 2: Replacing background for product images (Imagen 3 - Model: {IMAGEN3_MODEL_NAME})...")
        # if not PROJECT_ID or PROJECT_ID == "veo-testing":
        #     status_messages.append("  WARNING: Imagen 3 SDK not fully available or project not set. Using rembg+PIL simulation.")

        # for original_filename, product_local_path in local_product_image_paths.items():
        #     base, ext = os.path.splitext(original_filename); bg_added_filename = f"{base}_bg_added.png" 
        #     output_bg_added_local_path = os.path.join(dir_paths["bg_added_products"], bg_added_filename)
        #     processed_path = imagen3_replace_background(
        #         product_image_path=product_local_path,
        #         background_image_path=local_user_bg_path, 
        #         output_image_path=output_bg_added_local_path
        #     ) # model_name uses default
        #     if processed_path and os.path.exists(processed_path):
        #         bg_added_image_paths[original_filename] = processed_path
        #         status_messages.append(f"  BG replaced for {original_filename} -> {os.path.basename(processed_path)}")
        #     else:
        #         status_messages.append(f"  Failed to replace BG for {original_filename}.")
        
        # 3. Pair Slates and Process Each Pair
        product_slates = {}
        status_messages.append(f"\nStep 2: Pairing product slates for video processing...")
        for original_filename, product_local_path in local_product_image_paths.items():
            if "_first_slate" in original_filename: key = original_filename.split("_first_slate")[0]
            elif "_last_slate" in original_filename: key = original_filename.split("_last_slate")[0]
            else: continue
            if key not in product_slates: product_slates[key] = {}
            if "_first_slate" in original_filename: product_slates[key]['first'] = product_local_path
            elif "_last_slate" in original_filename: product_slates[key]['last'] = product_local_path
        
        status_messages.append(f"\nFound {len(product_slates)} potential product pairs for video processing.")
        all_extended_video_uris_for_concat = []

        for i, (product_base_name, slates) in enumerate(product_slates.items()):
            status_messages.append(f"\nProcessing product: {product_base_name} (Pair {i+1})")
            if 'first' in slates and 'last' in slates:
                first_slate_path_local = slates['first']
                last_slate_path_local = slates['last']

                # gcs_interpolated_video_blob = f"veo2_outputs/{run_id}/{product_base_name}_interpolated" # for simulation
                # status_messages.append(f"  Step 3a: Interpolating video (Veo 2 API Call with Bytes Attempt)...")

                # interpolated_video_gcs_uri = interpolate_video_veo2(
                #     start_image_path=first_slate_path_local,
                #     end_image_path=last_slate_path_local,
                #     prompt_text=VEO2_INTERPOLATION_PROMPT, # Veo2 needs GCS bucket for its output
                #     gcs_output_video_blob_name=gcs_interpolated_video_blob,
                # )
                
                interpolated_video_filename = f"{product_base_name}_interpolated"
                interpolated_local_video_path = os.path.join(dir_paths["interpolated_videos_local"], interpolated_video_filename)
                status_messages.append(f"  Step 3a: Interpolating video (Veo 2 API Call)...")
                interpolated_video_gcs_uri = interpolate_video_veo2(
                    first_slate_path_local, last_slate_path_local,
                    VEO2_INTERPOLATION_PROMPT, interpolated_local_video_path
                )

                if not interpolated_video_gcs_uri:
                    status_messages.append(f"  Veo 2 interpolation API call FAILED for {product_base_name}.")
                    continue
                status_messages.append(f"  Veo 2 interpolated video GCS URI: {interpolated_video_gcs_uri}")


                extended_video_local_filename = f"{product_base_name}_extended"
                extended_video_local_path = os.path.join(dir_paths["extended_videos_local"], extended_video_local_filename)
                status_messages.append(f"  Step 3b: Extending video (Veo 2 Simulation from local)...")
                extended_video_gcs_uri = extend_video_veo2(
                    interpolated_video_gcs_uri, VEO2_EXTENSION_PROMPT, extended_video_local_path
                )
                if extended_video_gcs_uri:
                    all_extended_video_uris_for_concat.append(extended_video_gcs_uri)
                    status_messages.append(f"  Extended video (local dummy) for {product_base_name} ready.")
                else: status_messages.append(f"  Extension (local dummy creation) failed.")
            else: status_messages.append(f"  Skipping {product_base_name}: Missing slate pair.")

        # 4. Concatenate All Extended Videos
        if all_extended_video_uris_for_concat:
            status_messages.append(f"\nStep 4: Concatenating {len(all_extended_video_uris_for_concat)} videos (will download from GCS if needed)...")
            temp_concatenated_video_filename = f"concatenated_video_temp_{run_id}.mp4" # Add .mp4
            temp_concatenated_video_path = os.path.join(dir_paths["concatenated_video_temp"], temp_concatenated_video_filename)
            concatenated_video_before_speed_change = concatenate_videos(
                all_extended_video_uris_for_concat, 
                temp_concatenated_video_path,
                run_temp_dir # Pass run_temp_dir for managing temporary downloads
            )
            
            if concatenated_video_before_speed_change:
                status_messages.append(f"  Videos concatenated into: {temp_concatenated_video_filename}")
                # 5. Alter Speed of Final Concatenated Video
                status_messages.append(f"\nStep 5: Altering speed of final concatenated video (Factor: {playback_speed:.2f})...")
                final_speed_altered_video_filename = f"final_video_speed_altered_{run_id}.mp4"
                final_speed_altered_video_path = os.path.join(dir_paths["final_output"], final_speed_altered_video_filename)
                final_local_path_for_gradio = alter_video_speed(
                    concatenated_video_before_speed_change, # Input is already a local path
                    final_speed_altered_video_path, 
                    playback_speed,
                    run_temp_dir # Pass run_temp_dir (though not strictly needed if input is local)
                )

                if final_local_path_for_gradio:
                    status_messages.append(f"  Speed altered for final video: {final_speed_altered_video_filename}")
                    # 6. Upload Final Video to GCS
                    status_messages.append(f"\nStep 6: Uploading final video to GCS...")
                    gcs_final_video_blob_name = f"final_videos/"
                    if upload_to_gcs(GCS_BUCKET_NAME, final_local_path_for_gradio, gcs_final_video_blob_name):
                        final_concatenated_video_gcs_uri = f"gs://{GCS_BUCKET_NAME}/{gcs_final_video_blob_name}"
                        status_messages.append(f"  Successfully uploaded final video to: {final_concatenated_video_gcs_uri}")
                    else: status_messages.append(f"  Failed to upload final video.")
                else: status_messages.append("  Speed alteration of concatenated video failed.")
            else: status_messages.append("  Video concatenation failed.")
        else: status_messages.append("\nNo videos were processed for concatenation.")

        final_video_for_display = None
        if final_local_path_for_gradio and os.path.exists(final_local_path_for_gradio) and 'gcs_final_video_blob_name' in locals():
            gradio_output_storage_dir = os.path.join(base_temp_dir, "gradio_final_videos")
            os.makedirs(gradio_output_storage_dir, exist_ok=True)
            
            # Use the same filename as on GCS for the local copy
            local_display_video_filename = os.path.basename(final_speed_altered_video_filename)
            local_display_video_path = os.path.join(gradio_output_storage_dir, local_display_video_filename)

            final_gcs_blob = f"{gcs_final_video_blob_name}{final_speed_altered_video_filename}"

            try:
                status_messages.append(f"  Downloading final video from GCS for UI display: gs://{GCS_BUCKET_NAME}/{gcs_final_video_blob_name}/{final_speed_altered_video_filename} to {local_display_video_path}")
                download_blob(GCS_BUCKET_NAME, final_gcs_blob, local_display_video_path)
                final_video_for_display = local_display_video_path
                gradio_video_path = f"/home/parulsahoo/CE-GitHub/zepto_prod/{final_video_for_display}"
                status_messages.append(f"  Successfully downloaded video for UI display to: {final_video_for_display}")
            except Exception as e_download_display:
                status_messages.append(f"  ERROR: Failed to download final video from GCS for UI display: {e_download_display}")
                final_video_for_display = local_display_video_path # Ensure it's None if download fails


        status_messages.append(f"\nPipeline finished successfully for Run ID: {run_id}.")
        return "\n".join(status_messages), final_video_for_display

    except Exception as e:
        status_messages.append(f"\nERROR: An unexpected error occurred in the pipeline: {e}")
        # Log the full traceback for debugging if needed in a real environment
        # import traceback
        # status_messages.append(f"Traceback: {traceback.format_exc()}")
        print(f"ERROR in pipeline (run_id: {run_id}): {e}") # Print to console as well
        return "\n".join(status_messages), final_video_for_display # Return None for GCS URI and local path on error
    
    finally:
        # Cleanup: Delete the run-specific temporary directory
        if os.path.exists(run_temp_dir):
            try:
                shutil.rmtree(run_temp_dir)
                status_messages.append(f"\nINFO: Temporary directory {run_temp_dir} cleaned up.")
                print(f"INFO: Cleaned up temporary directory: {run_temp_dir}")
            except Exception as e_cleanup:
                status_messages.append(f"\nWARNING: Failed to cleanup temporary directory {run_temp_dir}: {e_cleanup}")
                print(f"WARNING: Failed to cleanup temporary directory {run_temp_dir}: {e_cleanup}")

if __name__ == '__main__':
    print("video_gen.py executed directly (for testing purposes).")
    print(f"GCS_BUCKET_NAME: {GCS_BUCKET_NAME}")
    print(f"VERTEX_AI_PROJECT_ID: {PROJECT_ID}")
    print(f"VEO2_EXTENSION_PROMPT: {VEO2_EXTENSION_PROMPT}")
