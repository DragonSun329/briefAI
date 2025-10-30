#!/usr/bin/env python3
"""
Project Restructure Script

Reorganizes briefAI into:
- pipeline/ - Report generation (run on schedule)
- webapp/ - Streamlit + ask function (always-on)
- shared/ - Common utilities and data

This script creates symlinks to preserve the existing structure while
allowing both systems to work independently.
"""

import os
import shutil
from pathlib import Path

def main():
    """Restructure the project"""

    print("🔨 Starting project restructure...")
    print("="*70)

    # Base paths
    root = Path("/Users/dragonsun/briefAI")

    # Pipeline-only modules
    pipeline_modules = [
        "modules/web_scraper.py",
        "modules/batch_evaluator.py",
        "modules/news_evaluator.py",
        "modules/article_paraphraser.py",
        "modules/report_formatter.py",
        "modules/category_selector.py",
        "modules/entity_background_agent.py"
    ]

    # Webapp-only files
    webapp_files = [
        "app.py",
        "modules/article_qa_agent.py"
    ]

    # Shared files (used by both)
    shared_items = [
        "utils",      # All utilities
        "config",     # Configuration files
        "data",       # Data directory
        ".env"        # Environment variables
    ]

    # Step 1: Copy pipeline modules
    print("\n📦 Step 1: Setting up pipeline/")
    print("-"*70)
    for module_path in pipeline_modules:
        src = root / module_path
        if module_path.startswith("modules/"):
            dest = root / "pipeline" / module_path
        else:
            dest = root / "pipeline" / module_path

        dest.parent.mkdir(parents=True, exist_ok=True)

        if src.exists():
            shutil.copy2(src, dest)
            print(f"✅ Copied: {module_path} → {dest.relative_to(root)}")
        else:
            print(f"⚠️  Not found: {src}")

    # Copy orchestrator
    orchestrator_dir = root / "orchestrator"
    if orchestrator_dir.exists():
        dest_orchestrator = root / "pipeline" / "orchestrator"
        shutil.copytree(orchestrator_dir, dest_orchestrator, dirs_exist_ok=True)
        print(f"✅ Copied: orchestrator/ → pipeline/orchestrator/")

    # Copy pipeline entry point
    pipeline_entry = root / "run_orchestrated_pipeline.py"
    if pipeline_entry.exists():
        shutil.copy2(pipeline_entry, root / "pipeline" / "run_pipeline.py")
        print(f"✅ Copied: run_orchestrated_pipeline.py → pipeline/run_pipeline.py")

    # Step 2: Copy webapp files
    print("\n📱 Step 2: Setting up webapp/")
    print("-"*70)
    for file_path in webapp_files:
        src = root / file_path

        if file_path.startswith("modules/"):
            dest = root / "webapp" / "components" / file_path.replace("modules/", "")
        else:
            dest = root / "webapp" / file_path

        dest.parent.mkdir(parents=True, exist_ok=True)

        if src.exists():
            shutil.copy2(src, dest)
            print(f"✅ Copied: {file_path} → {dest.relative_to(root)}")
        else:
            print(f"⚠️  Not found: {src}")

    # Copy .streamlit config
    streamlit_dir = root / ".streamlit"
    if streamlit_dir.exists():
        dest_streamlit = root / "webapp" / ".streamlit"
        shutil.copytree(streamlit_dir, dest_streamlit, dirs_exist_ok=True)
        print(f"✅ Copied: .streamlit/ → webapp/.streamlit/")

    # Step 3: Create symlinks in shared/
    print("\n🔗 Step 3: Setting up shared/ (symlinks)")
    print("-"*70)
    for item in shared_items:
        src = root / item
        dest = root / "shared" / item

        if src.exists():
            # Remove existing symlink/dir if exists
            if dest.exists() or dest.is_symlink():
                if dest.is_symlink():
                    dest.unlink()
                elif dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()

            # Create relative symlink
            rel_src = os.path.relpath(src, dest.parent)
            os.symlink(rel_src, dest)
            print(f"✅ Linked: {item} → shared/{item}")
        else:
            print(f"⚠️  Not found: {src}")

    # Step 4: Create __init__.py files
    print("\n📝 Step 4: Creating __init__.py files")
    print("-"*70)
    init_dirs = [
        root / "pipeline",
        root / "pipeline" / "modules",
        root / "pipeline" / "utils",
        root / "webapp",
        root / "webapp" / "components",
        root / "webapp" / "utils",
        root / "shared"
    ]

    for init_dir in init_dirs:
        init_file = init_dir / "__init__.py"
        if not init_file.exists():
            init_file.touch()
            print(f"✅ Created: {init_file.relative_to(root)}")

    # Step 5: Create entry point scripts
    print("\n🚀 Step 5: Creating entry point scripts")
    print("-"*70)

    # Pipeline runner
    pipeline_runner = root / "pipeline" / "run_pipeline.sh"
    pipeline_runner.write_text("""#!/bin/bash
# Pipeline Runner - Generate weekly AI briefing report
cd "$(dirname "$0")"
python3 run_pipeline.py --top-n 12
""")
    pipeline_runner.chmod(0o755)
    print(f"✅ Created: pipeline/run_pipeline.sh")

    # Webapp runner
    webapp_runner = root / "webapp" / "run_webapp.sh"
    webapp_runner.write_text("""#!/bin/bash
# Webapp Runner - Start Streamlit interface
cd "$(dirname "$0")"
streamlit run app.py
""")
    webapp_runner.chmod(0o755)
    print(f"✅ Created: webapp/run_webapp.sh")

    print("\n" + "="*70)
    print("✅ Project restructure complete!")
    print()
    print("New structure:")
    print("  pipeline/")
    print("    ├── modules/          (report generation modules)")
    print("    ├── orchestrator/     (ACE orchestrator)")
    print("    ├── run_pipeline.py   (entry point)")
    print("    └── run_pipeline.sh   (convenience script)")
    print()
    print("  webapp/")
    print("    ├── components/       (Streamlit + ask function)")
    print("    ├── app.py           (entry point)")
    print("    └── run_webapp.sh    (convenience script)")
    print()
    print("  shared/")
    print("    ├── utils/           (symlink to ../utils)")
    print("    ├── config/          (symlink to ../config)")
    print("    ├── data/            (symlink to ../data)")
    print("    └── .env             (symlink to ../.env)")
    print()
    print("Next steps:")
    print("  1. Test pipeline: cd pipeline && ./run_pipeline.sh")
    print("  2. Test webapp: cd webapp && ./run_webapp.sh")
    print("  3. Update import paths if needed")

if __name__ == "__main__":
    main()
