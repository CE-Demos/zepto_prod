# Apparel Video Generation Pipeline

The project included an automted piepline which generated videos for multiple apparel products from their images and then concatenated the clips for different products together to make a campaign or ad video.

## Steps to set it up on local system

- Clone the repository.
- Create and initialize a Python virtual environment using `python -m venv <venvpath>` followed by `source <venvpath>/bin/activate`.
- Once the virtual environment is activated run `pip install -r requirements.txt` in the terminal to install all the dependencies.
- After installing all the dependencies in the root dir run `pyhton app.py` to initiate the gradio server. In case the initialization fails with an error as shown below, then try changing the SERVER_PORT value to `7860`.

  ![image](https://github.com/user-attachments/assets/179b92b1-715a-46d6-916f-1fa14625ba64)

- Open the link on a broswer and follow the text instruction on the app for image naming and uploading conventions. Set the parameters like playback speed and initial slates.
  The UI should look something like this.

  ![image](https://github.com/user-attachments/assets/cdc8303a-4ba6-4d08-8781-4df61e7cdd2d)

- Hit the generate button to kickstart the pipeline and wait for the result to show up on the UI. You can also download the output video.


## Steps to set up CI/CD and Deploy the app on Cloud Run

- Enable the following APIs in your GCP project:
    + Cloud Run API
    + Cloud Build API
    + Vertex AI API
    + Artifact Registry API

- Create a repository on Artifact Registry
    + Give it a suitable name and select the format `Docker`.
    + Leave the rest of the configurations as default and click create.

- Grant Cloud Build Permissions to Deploy on Cloud Run

    + ```
        # Find your project number
        PROJECT_NUMBER=$(gcloud projects describe $(gcloud config get-value project) --format='value(projectNumber)')
        
        # Grant Cloud Run Admin role to the Cloud Build service account
        gcloud projects add-iam-policy-binding $(gcloud config get-value project) \
            --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
            --role="roles/run.admin"
        
        # Grant IAM Service Account User role to the Cloud Build service account
        # This is necessary for deploying to Cloud Run
        gcloud projects add-iam-policy-binding $(gcloud config get-value project) \
            --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
            --role="roles/iam.serviceAccountUser"
      ```
      
    + Visit the Cloud Build Screen and click on Triggers from the left hand menu
        * Click on `Connect Repository`, select the GitHub repository with the app code after authenticating to your GitHub account.
        * Then create a trigger, give yor trigger a name and keep the Event as `Push to a branch`.
        * In the Configuration section select Type: Cloud Build configuration file (yaml or json).
        * Give the file location as `/cloudbuild.yaml`.
        * Select the service account with necessary permissions.
        * Hit `save`.

- Change the value of varibles in the Substitutions section of the `cloudbuild.yaml` file and the bucket names and API endpoints configured in the `video_gen.py` file according to your GCP project.
- Commit these changes and push to your repository. This will trigger the build and you can monitor the steps of creating the docker image and pushing it to the specified repository in your artifact registry.
- Following which you can see the newly created cloud run service and access the UI via the endpoint given for the service.
  
