# app.py
import gradio as gr
import os
from video_gen import process_images_and_generate_videos_pipeline
from video_gen import PROJECT_ID as vg_project_id # For startup warning

# --- Gradio App Logic Wrapper ---
def gradio_interface_handler(
    product_images_folder_list, # List of Gradio FileData objects
    background_image_file,      # Gradio FileData object for background image
    playback_speed: float
):
    if not product_images_folder_list:
        return "Error: No product images provided. Please upload a folder with .png, .jpeg, or .jpg files.", [], None
    if not background_image_file:
        return "Error: No background image provided. Please upload a .png, .jpeg, or .jpg file.", [], None
    
    # Basic server-side extension check (optional but good practice)
    allowed_extensions = ['.png', '.jpeg', '.jpg']
    
    # Check background image extension
    bg_filename = background_image_file.name
    if not os.path.splitext(bg_filename)[1].lower() in allowed_extensions:
        return f"Error: Background image must be one of {', '.join(allowed_extensions)}. Got: {bg_filename}", [], None

    # Check product images extensions
    for file_data in product_images_folder_list:
        prod_filename = file_data.name
        if not os.path.splitext(prod_filename)[1].lower() in allowed_extensions:
            return f"Error: All product images must be one of {', '.join(allowed_extensions)}. Found: {prod_filename}", [], None

    if playback_speed <= 0:
        return "Error: Playback speed must be greater than 0.", [], None

    product_image_temp_paths = product_images_folder_list
    user_background_image_temp_path = background_image_file.name

    status_log, processed_gcs_uris, generated_final_video_paths = \
        process_images_and_generate_videos_pipeline(
            product_image_temp_paths,
            user_background_image_temp_path,
            playback_speed
        )

    processed_gcs_uris_str = "\n".join(processed_gcs_uris) if processed_gcs_uris else "No images processed or uploaded to GCS."
    main_video_output = generated_final_video_paths

    

    return status_log, processed_gcs_uris_str, main_video_output


# --- Gradio Interface Definition ---
if not os.path.exists("temp_processing_space"):
    os.makedirs("temp_processing_space")

startup_warnings = []
if vg_project_id == "veo-testing":
    startup_warnings.append("WARNING: 'PROJECT_ID' in video_gen.py is not set. Imagen alteration of background image will be SIMULATED by copying.")

initial_description = (
    "1. Upload product images (filenames with 'productName_first_slate' or 'productName_last_slate').\n"
    "2. Upload your desired background image file. This background will FIRST be altered by Imagen using a hardcoded prompt (see video_gen.py).\n"
    "3. Set the playback speed for the generated videos (e.g., 1.0 for normal).\n"
    "4. Click 'Submit'.\n"
    "The system will: alter the uploaded background with Imagen, use 'rembg' to isolate products, composite products onto the Imagen-altered background, "
    "upload to GCS, simulate Veo 2 for interpolation, and simulate speed alteration."
)
if startup_warnings:
    initial_description += "\n\n" + "\n".join(startup_warnings)


iface = gr.Interface(
    fn=gradio_interface_handler,
    inputs=[
        gr.File(
            label="Product Images Folder/Files",
            file_count="multiple",
            file_types=['.png', '.jpeg', '.jpg', 'image/png', 'image/jpeg'] # Added MIME types for better compatibility
        ),
        gr.File(
            label="Background Image File (will be altered by Imagen)",
            type="filepath",
            file_types=['.png', '.jpeg', '.jpg', 'image/png', 'image/jpeg'] # Added MIME types
        ),
        gr.Number(
            label="Playback Speed Factor",
            value=1.0,
            minimum=0.1,
            maximum=2.0, 
            step=0.1,
            info="Enter playback speed (e.g., 0.5 slow, 1.0 normal, 2.0 fast). Suggested: 0.1-2.0"
        )
    ],
    outputs=[
        gr.Textbox(label="Status Log", lines=15, interactive=False),
        # gr.Textbox(label="Processed Images on GCS (URIs)", lines=5, interactive=False),
        gr.Video(label="Generated Video (First one, speed altered)")
    ],
    title="AI Product Video Pipeline (Imagen-Altered User BG + Veo Sim + Speed)",
    description=initial_description,
    allow_flagging="never",
)

if __name__ == "__main__":
    print("Starting Gradio App...")
    print("Please ensure 'video_gen.py' is in the same directory.")
    print("IMPORTANT: In 'video_gen.py', configure GCS_BUCKET_NAME, PROJECT_ID, LOCATION, and IMAGEN_MODEL_NAME.")
    # print(f"The hardcoded prompt in video_gen.py for Imagen background alteration is: '{HARDCODED_IMAGEN_BG_PROMPT}' (from video_gen.py).")
    print("Ensure GOOGLE_APPLICATION_CREDENTIALS environment variable is set for GCS and Vertex AI access.")
    print("Required libraries: gradio, google-cloud-storage, Pillow, rembg, google-cloud-aiplatform")
    iface.launch()