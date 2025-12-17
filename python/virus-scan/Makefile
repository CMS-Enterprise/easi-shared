.PHONY: help defs layer package clean deploy all upload-defs test

# Configuration
FUNCTION_NAME := s3-anti-virus-scan
LAYER_NAME := clamav-antivirus-layer
RUNTIME := python3.14
REGION := us-east-1
AV_DEFINITION_S3_BUCKET := aws-cms-cmmi-mint-dev-app-virus-scans
AV_DEFINITION_S3_PREFIX := clamav_defs

# Directories
DEFS_DIR := clamAV-def
LAYER_DIR := layer
DEPLOY_DIR := deploy

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
NC := \033[0m # No Color

help: ## Show this help message
	@echo "$(BLUE)ClamAV S3 Virus Scanner - Build System$(NC)"
	@echo ""
	@echo "$(GREEN)Available targets:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-15s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(GREEN)Quick start:$(NC)"
	@echo "  make all          # Build everything"
	@echo "  make deploy       # Deploy to AWS"

all: defs layer package ## Build everything (virus defs, layer, and package)
	@echo "$(GREEN)✓ All components built successfully!$(NC)"

defs: ## Download ClamAV virus definitions
	@echo "$(BLUE)=== Downloading ClamAV Virus Definitions ===$(NC)"
	@mkdir -p $(DEFS_DIR)
	@cd $(DEFS_DIR) && \
	for file in main.cvd daily.cvd bytecode.cvd; do \
		echo "Downloading $$file..."; \
		curl -f -L -o $$file http://database.clamav.net/$$file 2>/dev/null || \
		curl -f -L -o $$file https://packages.microsoft.com/clamav/$$file 2>/dev/null || \
		echo "Failed to download $$file"; \
	done
	@if [ ! -f "$(DEFS_DIR)/daily.cvd" ]; then \
		echo "Trying daily.cld as fallback..."; \
		cd $(DEFS_DIR) && curl -f -L -o daily.cld http://database.clamav.net/daily.cld; \
	fi
	@echo "$(GREEN)✓ Virus definitions downloaded to $(DEFS_DIR)/$(NC)"
	@ls -lh $(DEFS_DIR)/

upload-defs: defs ## Upload virus definitions to S3
	@echo "$(BLUE)=== Uploading Virus Definitions to S3 ===$(NC)"
	@aws s3 sync $(DEFS_DIR)/ s3://$(AV_DEFINITION_S3_BUCKET)/$(AV_DEFINITION_S3_PREFIX)/ \
		--exclude "*" --include "*.cvd" --include "*.cld"
	@echo "$(GREEN)✓ Virus definitions uploaded to s3://$(AV_DEFINITION_S3_BUCKET)/$(AV_DEFINITION_S3_PREFIX)/$(NC)"

layer: ## Build ClamAV Lambda layer
	@echo "$(BLUE)=== Building ClamAV Lambda Layer ===$(NC)"
	@mkdir -p $(LAYER_DIR)
	@docker build --platform linux/amd64 -t clamav-lambda-layer .
	@CONTAINER_ID=$$(docker create clamav-lambda-layer) && \
	docker cp $$CONTAINER_ID:/layer/clamav-layer.zip ./$(LAYER_DIR)/ && \
	docker rm $$CONTAINER_ID
	@echo "$(GREEN)✓ ClamAV layer built successfully!$(NC)"
	@echo "Layer location: $(LAYER_DIR)/clamav-layer.zip"
	@ls -lh $(LAYER_DIR)/clamav-layer.zip

package: ## Package Lambda function code
	@echo "$(BLUE)=== Packaging Lambda Function ===$(NC)"
	@rm -rf package
	@mkdir -p package $(DEPLOY_DIR)
	@cp scan.py update.py common.py clamav.py metrics.py package/
	@cd package && zip -r ../$(DEPLOY_DIR)/lambda-function.zip .
	@rm -rf package
	@echo "$(GREEN)✓ Lambda function packaged successfully!$(NC)"
	@echo "Package location: $(DEPLOY_DIR)/lambda-function.zip"
	@echo "Package size: $$(du -h $(DEPLOY_DIR)/lambda-function.zip | cut -f1)"

deploy: package ## Deploy Lambda function to AWS
	@echo "$(BLUE)=== Deploying Lambda Function ===$(NC)"
	@aws lambda update-function-code \
		--function-name $(FUNCTION_NAME) \
		--zip-file fileb://$(DEPLOY_DIR)/lambda-function.zip \
		--region $(REGION)
	@echo "$(GREEN)✓ Lambda function deployed successfully!$(NC)"

deploy-layer: layer ## Deploy Lambda layer to AWS
	@echo "$(BLUE)=== Publishing Lambda Layer ===$(NC)"
	@aws lambda publish-layer-version \
		--layer-name $(LAYER_NAME) \
		--description "ClamAV binaries and libraries for virus scanning" \
		--zip-file fileb://$(LAYER_DIR)/clamav-layer.zip \
		--compatible-runtimes $(RUNTIME) \
		--compatible-architectures x86_64 \
		--region $(REGION)
	@echo "$(GREEN)✓ Lambda layer published successfully!$(NC)"

config: ## Update Lambda function environment variables
	@echo "$(BLUE)=== Updating Lambda Configuration ===$(NC)"
	@aws lambda update-function-configuration \
		--function-name $(FUNCTION_NAME) \
		--environment Variables='{ \
			"AV_DEFINITION_S3_BUCKET":"$(AV_DEFINITION_S3_BUCKET)", \
			"AV_DEFINITION_S3_PREFIX":"$(AV_DEFINITION_S3_PREFIX)/", \
			"ENV":"dev" \
		}' \
		--region $(REGION)
	@echo "$(GREEN)✓ Lambda configuration updated!$(NC)"

test: ## Test Lambda function with sample event
	@echo "$(BLUE)=== Testing Lambda Function ===$(NC)"
	@echo '{"Records":[{"s3":{"bucket":{"name":"aws-cms-cmmi-mint-dev-app-file-uploads"},"object":{"key":"test/test.txt"}}}]}' | \
	aws lambda invoke \
		--function-name $(FUNCTION_NAME) \
		--payload file:///dev/stdin \
		--region $(REGION) \
		response.json
	@cat response.json | python3 -m json.tool
	@rm -f response.json
	@echo "$(GREEN)✓ Test complete!$(NC)"

clean: ## Clean build artifacts
	@echo "$(BLUE)=== Cleaning Build Artifacts ===$(NC)"
	@rm -rf package
	@rm -rf $(DEPLOY_DIR)
	@rm -rf $(LAYER_DIR)
	@rm -rf $(DEFS_DIR)
	@docker rmi clamav-lambda-layer 2>/dev/null || true
	@echo "$(GREEN)✓ Clean complete!$(NC)"

info: ## Show current configuration
	@echo "$(BLUE)=== Configuration ===$(NC)"
	@echo "Function Name:     $(FUNCTION_NAME)"
	@echo "Layer Name:        $(LAYER_NAME)"
	@echo "Runtime:           $(RUNTIME)"
	@echo "Region:            $(REGION)"
	@echo "Virus Defs Bucket: $(AV_DEFINITION_S3_BUCKET)"
	@echo "Virus Defs Prefix: $(AV_DEFINITION_S3_PREFIX)"
	@echo ""
	@echo "$(BLUE)=== Status ===$(NC)"
	@if [ -d "$(DEFS_DIR)" ]; then echo "$(GREEN)✓$(NC) Virus definitions exist"; else echo "$(YELLOW)✗$(NC) Virus definitions not built"; fi
	@if [ -f "$(LAYER_DIR)/clamav-layer.zip" ]; then echo "$(GREEN)✓$(NC) Lambda layer exists"; else echo "$(YELLOW)✗$(NC) Lambda layer not built"; fi
	@if [ -f "$(DEPLOY_DIR)/lambda-function.zip" ]; then echo "$(GREEN)✓$(NC) Lambda package exists"; else echo "$(YELLOW)✗$(NC) Lambda package not built"; fi
