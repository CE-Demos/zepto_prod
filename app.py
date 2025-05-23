# app.py
import gradio as gr
import os
from video_gen import process_images_and_generate_videos_pipeline
from video_gen import PROJECT_ID as vg_project_id # For startup warning

# --- Gradio App Logic Wrapper ---
def gradio_interface_handler(
    product_images_folder_list, # List of Gradio FileData objects
    #background_image_file,      # Gradio FileData object for background image
    playback_speed: float
):
    # if not product_images_folder_list:
    #     return "Error: No product images provided. Please upload a folder with .png, .jpeg, or .jpg files.", [], None
    # if not background_image_file:
    #     return "Error: No background image provided. Please upload a .png, .jpeg, or .jpg file.", [], None
    
    # Basic server-side extension check (optional but good practice)
    allowed_extensions = ['.png', '.jpeg', '.jpg']
    
    # Check background image extension
    # bg_filename = background_image_file.name
    # if not os.path.splitext(bg_filename)[1].lower() in allowed_extensions:
    #     return f"Error: Background image must be one of {', '.join(allowed_extensions)}. Got: {bg_filename}", [], None

    # Check product images extensions
    for file_data in product_images_folder_list:
        prod_filename = file_data.name
        if not os.path.splitext(prod_filename)[1].lower() in allowed_extensions:
            return f"Error: All product images must be one of {', '.join(allowed_extensions)}. Found: {prod_filename}", [], None

    if playback_speed <= 0:
        return "Error: Playback speed must be greater than 0.", [], None

    product_image_temp_paths = product_images_folder_list
    #user_background_image_temp_path = background_image_file.name

    status_log, generated_final_video_paths = \
        process_images_and_generate_videos_pipeline(
            product_image_temp_paths,
            # user_background_image_temp_path,
            playback_speed
        )

    # processed_gcs_uris_str = "\n".join(processed_gcs_uris) if processed_gcs_uris else "No images processed or uploaded to GCS."
    main_video_output = generated_final_video_paths

    print(f"DEBUG: Path being sent to Gradio gr.Video: '{main_video_output}'") # Added quotes for clarity
    if main_video_output and isinstance(main_video_output, str):
        abs_video_path = os.path.abspath(main_video_output)
        print(f"DEBUG: Absolute video path: '{abs_video_path}'")
        print(f"DEBUG: Current working directory: '{os.getcwd()}'")
        if not os.path.exists(abs_video_path): # Check absolute path
            print(f"DEBUG: WARNING! Gradio video path exists check FAILED (absolute): '{abs_video_path}'")
        else:
            print(f"DEBUG: Gradio video path exists check PASSED (absolute): '{abs_video_path}'")
            try:
                file_size = os.path.getsize(abs_video_path)
                print(f"DEBUG: Video file size: {file_size} bytes")
                if file_size == 0:
                    print(f"DEBUG: WARNING! Video file size is 0 bytes for '{abs_video_path}'.")
            except OSError as e:
                print(f"DEBUG: Error getting file size for {abs_video_path}: {e}")
    elif main_video_output is None:
        print(f"DEBUG: main_video_output is None. No video will be displayed.")
    else:
        print(f"DEBUG: main_video_output is not a string or None. Type: {type(main_video_output)}, Value: '{main_video_output}'")

    return status_log, main_video_output


# --- Gradio Interface Definition ---
if not os.path.exists("temp_processing_space"):
    os.makedirs("temp_processing_space")

startup_warnings = []
if not vg_project_id == "veo-testing":
    startup_warnings.append("WARNING: 'PROJECT_ID' in video_gen.py is not set. Imagen alteration of background image will be SIMULATED by copying.")

initial_description = (
    "1. Upload product images (filenames with 'productName_first_slate' or 'productName_last_slate').\n"
   # "2. Upload your desired background image file. This background will FIRST be altered by Imagen using a hardcoded prompt (see video_gen.py).\n"
    "3. Set the playback speed for the generated videos (e.g., 1.0 for normal).\n"
    "4. Click 'Submit'.\n"
    "The system will: isolate product images, create first_slate end_slate pairs for product, "
    "simulate Veo 2 for interpolation, and simulate speed alteration."
)
if startup_warnings:
    initial_description += "\n\n" + "\n".join(startup_warnings)

gradio_video_serve_dir = os.path.join("temp_processing_space", "gradio_final_videos")

if not os.path.exists(gradio_video_serve_dir):
    os.makedirs(gradio_video_serve_dir, exist_ok=True)

# iface = gr.Interface(
#     fn=gradio_interface_handler,
#     inputs=[
#         gr.File(
#             label="Product Images Folder/Files",
#             file_count="multiple",
#             file_types=['.png', '.jpeg', '.jpg', 'image/png', 'image/jpeg'] # Added MIME types for better compatibility
#         ),
#         # gr.File(
#         #     label="Background Image File (will be altered by Imagen)",
#         #     type="filepath",
#         #     file_types=['.png', '.jpeg', '.jpg', 'image/png', 'image/jpeg'] # Added MIME types
#         # ),
#         gr.Number(
#             label="Playback Speed Factor",
#             value=1.0,
#             minimum=0.1,
#             maximum=2.0, 
#             step=0.1,
#             info="Enter playback speed (e.g., 0.5 slow, 1.0 normal, 2.0 fast). Suggested: 0.1-2.0"
#         )
#     ],
#     outputs=[
#         gr.Textbox(label="Status Log", lines=15, interactive=False),
#         # gr.Textbox(label="Processed Images on GCS (URIs)", lines=5, interactive=False),
#         gr.Video(label="Generated Video (Concatenated and speed altered)")
#     ],
#     title="AI Product Video Generation",
#     description=initial_description,
#     allow_flagging="never",
# )

with gr.Blocks(theme=gr.themes.Soft()) as demo:
    gr.Markdown("# Zepto Apparel Videofication tool")
    gr.Markdown(initial_description)

    with gr.Row():
        with gr.Column(scale=1):
            product_images_input = gr.File(
                label="Upload Product Images (select multiple .png, .jpeg, .jpg)",
                file_count="multiple",
                file_types=['.png', '.jpeg', '.jpg', 'image/png', 'image/jpeg']
            )
            
            playback_speed_input = gr.Number(
                label="Playback Speed Factor for Final Video",
                value=1.0,
                minimum=0.1,
                maximum=5.0,
                step=0.1,
                info="e.g., 0.5 (slow), 1.0 (normal), 2.0 (fast)"
            )
            generate_button = gr.Button("Generate All Videos", variant="primary")
        
        with gr.Column(scale=2):
            status_log_output = gr.Textbox(
                label="Pipeline Status Log", 
                lines=15, 
                interactive=False,
                show_copy_button=True
            )
            
            video_display_output = gr.Video(
                label="Final Generated Video",
                # Gradio will offer download for .txt if it can't render.
                # For actual video, provide a path to an .mp4 or similar.
                # format="mp4", # You can suggest a format if you know it
                # height=480, # Optional: set height
                # width=640  # Optional: set width
            )

    generate_button.click(
        fn=gradio_interface_handler,
        inputs=[
            product_images_input,
            playback_speed_input
        ],
        outputs=[
            status_log_output,
            video_display_output
        ]
    )


if __name__ == "__main__":
    print("Starting Gradio App...")
    print("Please ensure 'video_gen.py' is in the same directory.")
    print("IMPORTANT: In 'video_gen.py', configure GCS_BUCKET_NAME, PROJECT_ID, LOCATION, and IMAGEN_MODEL_NAME.")
    # print(f"The hardcoded prompt in video_gen.py for Imagen background alteration is: '{HARDCODED_IMAGEN_BG_PROMPT}' (from video_gen.py).")
    print("Ensure GOOGLE_APPLICATION_CREDENTIALS environment variable is set for GCS and Vertex AI access.")
    print("Required libraries: gradio, google-cloud-storage, Pillow, rembg, google-cloud-aiplatform")
    demo.launch(server_name="0.0.0.0", server_port=8080)