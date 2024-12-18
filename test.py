import os
import re
import subprocess
import tempfile
import shutil
import requests
from datetime import datetime

# CONFIGURATION: Replace with your actual GitHub token
GITHUB_TOKEN = ""

def check_command(command_name):
    if not shutil.which(command_name):
        raise FileNotFoundError(
            f"The command '{command_name}' is not installed or not in the system PATH."
        )

def run_command(command, cwd=None, check=True):
    try:
        print(f"Running command: {' '.join(command)} in {cwd or os.getcwd()}")
        result = subprocess.run(
            command,
            cwd=cwd,
            check=check,
            capture_output=True,
            text=True
        )
        print(f"Command output: {result.stdout.strip()}")
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {' '.join(command)}")
        print(f"Error output: {e.stderr.strip()}")
        raise e

def clone_repo(repo_name, org='gmi-platform'):
    repo_url = f'https://{GITHUB_TOKEN}@github.com/{org}/{repo_name}.git'
    temp_dir = tempfile.mkdtemp()

    try:
        print(f"Cloning repository: {repo_url}")
        run_command(['git', 'clone', repo_url, temp_dir])
        return temp_dir
    except subprocess.CalledProcessError:
        print(f"Error cloning repository {repo_name}. Check if the repo exists and the token is valid.")
        return None

def find_tf_files(directory):
    tf_files = []
    for root, _, files in os.walk(directory):
        tf_files.extend([
            os.path.join(root, file)
            for file in files
            if file.endswith('.tf')
        ])
    return tf_files

def replace_module_source(content):
    """
    Updates the source and version fields only for Infoblox module blocks.
    Preserves comments and skips commented-out blocks.
    """
    # Define the specific source pattern
    specific_source_pattern = r'source\s*=\s*"terraform\.generalmills\.com/generalmills/iaas/gmi//modules/infoblox-record"'
    new_source = 'source = "artifactory.genmills.com/terraform-module-local__generalmills/infoblox-record/gmi//modules/infoblox-record"'
    new_version = 'version = "~> 0.1"\n'

    # Regex pattern to match module blocks
    module_pattern = (
        r'(module\s*".*?"\s*{)'  # Capture the module header
        r'([^}]*?)'  # Capture all the lines within the module block
        r'(})'  # Capture the closing brace
    )

    def update_module(match):
        """
        Updates the source and version fields in the matched module block.
        Preserves comments and skips commented-out blocks.
        """
        module_header = match.group(1)
        module_body = match.group(2)
        closing_brace = match.group(3)

        # Check if the specific source is commented out
        if re.search(r'#.*' + specific_source_pattern, module_body):
            return match.group(0)

        # Check if the specific source pattern exists in the module body
        if re.search(specific_source_pattern, module_body):
            # Check if source or version lines are commented out
            lines = module_body.split('\n')
            uncommented_lines = [
                line for line in lines 
                if not line.strip().startswith('#')
            ]

            # Only proceed if source is not commented out
            if not any('#' + line.strip() in lines for line in uncommented_lines):
                # Replace the source
                module_body = re.sub(
                    specific_source_pattern, 
                    new_source, 
                    module_body
                )

                # Remove all existing version attributes
                version_pattern = r'\s*version\s*=\s*".*?"\n?'
                module_body = re.sub(version_pattern, '', module_body, count=1)

                # Remove any additional version attributes
                while re.search(version_pattern, module_body):
                    module_body = re.sub(version_pattern, '', module_body, count=1)

                # Ensure other arguments are on a new line if they're not already
                module_body = re.sub(
                    r'(version = "~> 0.1")(\s*\w+\s*=)', 
                    r'\1\n  \2', 
                    module_body
                )

                # Add the new version attribute after the source
                module_body = re.sub(
                    new_source, 
                    f"{new_source}\n  {new_version}", 
                    module_body
                )

        # Return the module block (modified or unchanged)
        return f"{module_header}{module_body}{closing_brace}"

    # Apply the regex substitution to update only the relevant lines
    updated_content = re.sub(module_pattern, update_module, content, flags=re.DOTALL)
    
    # Check if any changes were made
    if updated_content != content:
        print("Module source and version updated.")
        return updated_content
    
    return content

def run_terraform_fmt(directory):
    try:
        run_command(['terraform', 'fmt', '--recursive'], cwd=directory)
        print("Terraform files formatted successfully.")
    except subprocess.CalledProcessError:
        print("Error formatting Terraform files.")
        raise

def create_pull_request(repo_name, branch_name, pr_title, pr_body, org='gmi-platform'):
    url = f"https://api.github.com/repos/{org}/{repo_name}/pulls"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "title": pr_title,
        "body": pr_body,
        "head": branch_name,
        "base": "main"
    }

    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 201:
        pr_url = response.json().get("html_url")
        print(f"Pull Request created: {pr_url}")
        return pr_url
    else:
        print(f"Failed to create Pull Request: {response.json()}")
        return None

def update_and_pr_repo(repo_name):
    print(f"\nProcessing repository: {repo_name}")

    repo_path = clone_repo(repo_name)
    if not repo_path:
        print(f"Skipping repository {repo_name} due to clone error.")
        return False

    try:
        os.chdir(repo_path)
        tf_files = find_tf_files(repo_path)
        if not tf_files:
            print(f"No Terraform files found in {repo_name}.")
            return False

        files_modified = False

        for tf_file in tf_files:
            with open(tf_file, 'r', encoding='utf-8') as f:
                content = f.read()

            new_content = replace_module_source(content)

            if new_content != content:
                files_modified = True
                with open(tf_file, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"Updated file: {tf_file}")

        if files_modified:
            run_terraform_fmt(repo_path)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            branch_name = f"update-infoblox-module-{timestamp}"
            run_command(['git', 'checkout', '-b', branch_name])
            run_command(['git', 'add', '.'])
            commit_message = "Update Infoblox Terraform Module Source and Version\n\n"
            run_command(['git', 'commit', '-m', commit_message])
            run_command(['git', 'push', 'origin', branch_name])

            pr_title = f"Update Infoblox Module Source and Version"
            pr_body = "Automated update of Terraform module source and version:\n\n"
            pr_url = create_pull_request(repo_name, branch_name, pr_title, pr_body)
            if pr_url:
                with open('pr_links.txt', 'a', encoding='utf-8') as pr_file:
                    pr_file.write(f"{repo_name}: {pr_url}\n")
        else:
            print(f"No changes needed for {repo_name}.")

        return True

    except Exception as e:
        print(f"Error processing {repo_name}: {e}")
        return False

    finally:
        os.chdir(os.path.expanduser('~'))
        shutil.rmtree(repo_path, onerror=lambda func, path, exc_info: os.chmod(path, 0o777) or func(path))

def main():
    for tool in ['git', 'terraform']:
        try:
            check_command(tool)
        except FileNotFoundError as e:
            print(e)
            return

    repos = [
'terraform-eapps-dash-ent-gcp',
    ]

    for repo in repos:
        update_and_pr_repo(repo)

if __name__ == '__main__':
    main()