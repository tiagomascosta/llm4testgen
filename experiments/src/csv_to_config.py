import csv
import json
from pathlib import Path

# Configuration: Add repositories to exclude here
EXCLUDED_REPOS = [
    # Add repo URLs to exclude, for example:
    # "https://github.com/user/repo.git",
    # "https://github.com/another/repo.git",
    
    # Repositories with issues:
    "https://github.com/aws/aws-secretsmanager-jdbc.git",  # Some tests have compilation issues
    "https://github.com/aws/event-ruler.git",  # Takes too long to clone
    "https://github.com/fusesource/jansi.git",  # Exclude Jansi repository
    "https://github.com/assertj/assertj-vavr.git",  # Exclude AssertJ Vavr repository
    "https://github.com/giraud/reasonml-idea-plugin.git",  # Exclude ReasonML IDEA plugin repository
    "https://github.com/iipc/jwarc.git"  # Exclude JWARC repository
]

def extract_class_from_path(bug_file_path):
    """
    Extract class name from bug_file_path using the described algorithm:
    1. Split by "/"
    2. Remove the .java extension from the last element (the class file)
    3. Find the first occurrence of "java" or "main" from the end
    4. Take everything from that position onwards (excluding "java" or "main")
    """
    # Split the path by "/"
    parts = bug_file_path.split('/')
    
    # Remove the .java extension from the last element (the class file)
    if parts and parts[-1].endswith('.java'):
        parts[-1] = parts[-1][:-5]  # Remove '.java' extension
    
    # Find the first occurrence of "java" or "main" from the end
    cut_point = None
    for i in range(len(parts) - 1, -1, -1):
        if parts[i] in ['java', 'main']:
            cut_point = i + 1  # Start from the position after java/main
            break
    
    if cut_point is None:
        # If no java/main found, use the entire path
        cut_point = 0
    
    # Take everything from cut_point onwards
    class_parts = parts[cut_point:]
    
    # Join with dots to create the class name
    class_name = '.'.join(class_parts)
    
    return class_name

def csv_to_config(csv_path, output_path):
    """
    Convert CSV file to batch runner config format
    """
    config = []
    excluded_count = 0
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            try:
                # Extract required fields
                repo_url = row['repo_url']
                commit_hash = row['bug_commit_hash']
                fix_commit_hash = row['fix_commit_hash']
                method_name = row['method_name']
                bug_file_path = row['bug_file_path']
                
                # Check if repository should be excluded
                if repo_url in EXCLUDED_REPOS:
                    excluded_count += 1
                    print(f"Excluding repository: {repo_url}")
                    continue
                
                # Extract class name from bug_file_path
                class_name = extract_class_from_path(bug_file_path)
                
                # Build method signature
                method = f"{class_name}#{method_name}"
                
                config.append({
                    "repo_url": repo_url,
                    "commit_hash": commit_hash,
                    "fix_commit_hash": fix_commit_hash,
                    "method": method
                })
                
            except Exception as e:
                print(f"Error processing row: {e}")
                print(f"Row data: {row}")
                continue
    
    # Write config to file
    with open(output_path, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"Generated config with {len(config)} repositories")
    if excluded_count > 0:
        print(f"Excluded {excluded_count} repositories")
    print(f"Config saved to: {output_path}")

if __name__ == "__main__":
    # Generate config for sample.csv
    sample_csv_path = Path(__file__).parent.parent / "dataset" / "src" / "sample.csv"
    sample_output_path = Path(__file__).parent / "sample_config.json"
    print("Generating config for sample.csv...")
    csv_to_config(sample_csv_path, sample_output_path)
    
    # Generate config for subsample.csv
    subsample_csv_path = Path(__file__).parent.parent / "dataset" / "src" / "subsample.csv"
    subsample_output_path = Path(__file__).parent / "subsample_config.json"
    print("\nGenerating config for subsample.csv...")
    csv_to_config(subsample_csv_path, subsample_output_path) 