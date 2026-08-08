# Asset Model Pool Specification

共享模型池，管理 Checkpoint/LoRA/VAE/ControlNet，支持 CivitAI 集成。

## ADDED Requirements

### Requirement: Shared model pool directory
The system SHALL manage a centralized model storage directory structure.

#### Scenario: Model directory structure
- **WHEN** system initializes model pool
- **THEN** creates directories: Stable-diffusion/, Lora/, VAE/, ControlNet/, Embedding/, Upscale/, 3d/

### Requirement: Model registration
The system SHALL register AI models into the asset management system.

#### Scenario: Register checkpoint model
- **WHEN** user adds SDXL checkpoint to model pool
- **THEN** system creates AssetNode(type="model", model_type="checkpoint") with file_path, hash, metadata

### Requirement: Model type classification
The system SHALL classify models by type.

#### Scenario: Model types
- **WHEN** models are registered
- **THEN** model_type can be: checkpoint, lora, vae, controlnet, embedding, upscaler

### Requirement: Base model tracking
The system SHALL track which base model a model is designed for.

#### Scenario: Base model field
- **WHEN** registering LoRA "cyberpunk_style"
- **THEN** system stores base_model="SDXL" indicating it works with SDXL checkpoints

### Requirement: Model file hash verification
The system SHALL calculate and store SHA256 hashes for model files.

#### Scenario: Hash calculation
- **WHEN** user adds model file "sdxl_v1.safetensors"
- **THEN** system calculates SHA256 and stores in model.file_hash for integrity verification

### Requirement: CivitAI integration
The system SHALL integrate with CivitAI for model discovery and download.

#### Scenario: Search CivitAI
- **WHEN** user searches CivitAI for "cyberpunk style"
- **THEN** system returns matching models with metadata, preview images, download links

#### Scenario: Download from CivitAI
- **WHEN** user clicks download on CivitAI model
- **THEN** system downloads to appropriate pool directory and registers as AssetNode

### Requirement: CivitAI model linking
The system SHALL store CivitAI IDs for downloaded models.

#### Scenario: Store CivitAI IDs
- **WHEN** downloading model with CivitAI ID 12345
- **THEN** system stores civitai_model_id="12345", civitai_version_id for version tracking

### Requirement: LoRA trigger words
The system SHALL store and display LoRA trigger words.

#### Scenario: Trigger words for LoRA
- **WHEN** registering LoRA "cyberpunk_neon"
- **THEN** system stores trigger_words="cyberpunk, neon lights" for user reference

### Requirement: Model preview images
The system SHALL store preview images from CivitAI.

#### Scenario: Preview storage
- **WHEN** downloading CivitAI model with preview images
- **THEN** system stores preview_urls as JSON array

### Requirement: Recommended weight settings
The system SHALL store recommended weight ranges for LoRA models.

#### Scenario: Weight recommendation
- **WHEN** registering LoRA
- **THEN** system stores recommended_weight (default 1.0) and weight_range for user guidance

### Requirement: Model pool scanning
The system SHALL scan directories to discover and register new models.

#### Scenario: Scan model directory
- **WHEN** admin triggers scan
- **THEN** system scans Lora/, Checkpoint/, etc. directories
- **AND** registers new models found, updates existing model metadata

### Requirement: ComfyUI model discovery
The system SHALL enable ComfyUI to discover models from the shared pool.

#### Scenario: ComfyUI model path
- **WHEN** ComfyUI loads
- **THEN** it reads model paths from backend configuration
- **AND** lists available models from shared pool

### Requirement: Model usage tracking
The system SHALL track which models are used in asset generations.

#### Scenario: Usage logging
- **WHEN** asset is generated with SDXL + LoRA_cyber
- **THEN** lineage records include model IDs for both checkpoint and LoRA

### Requirement: Training resolution metadata
The system SHALL store recommended training resolution for models.

#### Scenario: Training resolution
- **WHEN** registering LoRA
- **THEN** system can store training_resolution="512x768" as guidance for optimal results

### Requirement: Model deletion with asset protection
The system SHALL warn before deleting models that are referenced in assets.

#### Scenario: Deletion protection
- **WHEN** user attempts to delete model "LoRA_cyber" used in 50 assets
- **THEN** system warns user and lists dependent assets
- **AND** requires confirmation to proceed
