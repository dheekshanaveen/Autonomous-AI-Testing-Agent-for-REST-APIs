"""OpenAPI Specification Reader for Autonomous AI Testing Agent.

Parses OpenAPI 3.0.x and 3.1.x specifications from URLs, local files, or raw dicts
into structured, strongly-typed Python objects for downstream test generation.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union
import httpx
from pydantic import BaseModel, Field


# ------------------------------------------------------------------------------
# Custom Exception Hierarchy
# ------------------------------------------------------------------------------

class SpecReaderError(Exception):
    """Base exception for all OpenAPI specification reading errors."""


class SpecConnectionError(SpecReaderError):
    """Raised when the remote OpenAPI specification URL cannot be reached."""


class SpecNotFoundError(SpecReaderError):
    """Raised when a local specification file does not exist."""


class SpecParseError(SpecReaderError):
    """Raised when the specification contains invalid or malformed JSON."""


class SpecValidationError(SpecReaderError):
    """Raised when the document lacks required OpenAPI structure."""


class SpecResolutionError(SpecReaderError):
    """Raised when a component reference ($ref) cannot be resolved."""


# ------------------------------------------------------------------------------
# Structured Data Models
# ------------------------------------------------------------------------------

class ParameterDefinition(BaseModel):
    """Details for a path, query, header, or cookie parameter."""

    name: str = Field(..., description="Parameter name")
    location: str = Field(..., description="Location: 'path', 'query', 'header', or 'cookie'")
    required: bool = Field(default=False, description="Whether the parameter is mandatory")
    description: Optional[str] = Field(default=None, description="Human-readable description")
    schema_info: Optional[Dict[str, Any]] = Field(default=None, description="Resolved JSON schema of the parameter")


class RequestBodyDefinition(BaseModel):
    """Details for an operation's request body."""

    required: bool = Field(default=False, description="Whether a request body is required")
    description: Optional[str] = Field(default=None, description="Description of the request body")
    content_types: List[str] = Field(default_factory=list, description="Accepted media types (e.g. application/json)")
    schemas: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Resolved JSON schemas keyed by media type",
    )


class ResponseDefinition(BaseModel):
    """Details for an operation's documented HTTP response."""

    status_code: str = Field(..., description="HTTP status code (e.g. '200', '404', or 'default')")
    description: Optional[str] = Field(default=None, description="Response description")
    content_types: List[str] = Field(default_factory=list, description="Response media types")
    schemas: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Resolved JSON schemas keyed by media type",
    )
    links: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Explicit OpenAPI links defined on this response",
    )


class SecurityRequirement(BaseModel):
    """A single security requirement mapping scheme name to requested scopes."""

    scheme_name: str = Field(..., description="Name of the security scheme (e.g. 'HTTPBearer')")
    scopes: List[str] = Field(default_factory=list, description="Required OAuth2 scopes, if applicable")


class SecuritySchemeDefinition(BaseModel):
    """Definition of an authentication mechanism."""

    name: str = Field(..., description="Security scheme identifier")
    type: str = Field(..., description="Scheme type: 'http', 'apiKey', 'oauth2', or 'openIdConnect'")
    scheme: Optional[str] = Field(default=None, description="HTTP authorization scheme (e.g. 'bearer', 'basic')")
    bearer_format: Optional[str] = Field(default=None, description="Bearer token format (e.g. 'JWT')")
    location: Optional[str] = Field(default=None, description="Parameter location for apiKey ('header', 'query', 'cookie')")
    parameter_name: Optional[str] = Field(default=None, description="Name of header/query param for apiKey")
    description: Optional[str] = Field(default=None, description="Description of the security scheme")


class OperationDefinition(BaseModel):
    """Structured details for a single API endpoint operation (e.g. GET /orders/{id})."""

    operation_id: Optional[str] = Field(default=None, description="Unique operation identifier")
    method: str = Field(..., description="HTTP method in uppercase (GET, POST, etc.)")
    path: str = Field(..., description="URL path template (e.g. /orders/{order_id})")
    summary: Optional[str] = Field(default=None, description="Short summary of the operation")
    description: Optional[str] = Field(default=None, description="Detailed operation description")
    tags: List[str] = Field(default_factory=list, description="Categorization tags")
    parameters: List[ParameterDefinition] = Field(default_factory=list, description="All applicable parameters")
    request_body: Optional[RequestBodyDefinition] = Field(default=None, description="Request body specification if defined")
    responses: Dict[str, ResponseDefinition] = Field(default_factory=dict, description="Documented responses by status code")
    security: List[SecurityRequirement] = Field(default_factory=list, description="Security requirements for this operation")
    links: Dict[str, Dict[str, Any]] = Field(default_factory=dict, description="Explicit OpenAPI links from all responses")


class APISpecification(BaseModel):
    """Complete structured representation of an OpenAPI document."""

    title: str = Field(..., description="API title")
    version: str = Field(..., description="API specification version")
    openapi_version: str = Field(..., description="OpenAPI version string (e.g. '3.1.0')")
    description: Optional[str] = Field(default=None, description="API description")
    base_url: Optional[str] = Field(default=None, description="Default server URL if configured")
    endpoints: List[str] = Field(default_factory=list, description="List of unique URL paths")
    operations: List[OperationDefinition] = Field(default_factory=list, description="List of all endpoint operations")
    security_schemes: Dict[str, SecuritySchemeDefinition] = Field(
        default_factory=dict,
        description="Declared security schemes",
    )
    global_security: List[SecurityRequirement] = Field(
        default_factory=list,
        description="Global security requirements",
    )
    components: Dict[str, Any] = Field(default_factory=dict, description="Raw components section")
    raw_spec: Dict[str, Any] = Field(default_factory=dict, description="Complete raw OpenAPI dictionary")

    def get_operations_by_path(self, path: str) -> List[OperationDefinition]:
        """Return all operations for a specific path."""
        return [op for op in self.operations if op.path == path]

    def get_operation(self, method: str, path: str) -> Optional[OperationDefinition]:
        """Find a single operation matching the method and path."""
        method_upper = method.upper()
        for op in self.operations:
            if op.method == method_upper and op.path == path:
                return op
        return None

    def get_operations_requiring_auth(self) -> List[OperationDefinition]:
        """Return all operations that enforce security requirements."""
        return [op for op in self.operations if len(op.security) > 0]


# ------------------------------------------------------------------------------
# Specification Reader Implementation
# ------------------------------------------------------------------------------

class OpenAPISpecReader:
    """Reader and parser for OpenAPI 3.0 and 3.1 specifications."""

    HTTP_METHODS: Set[str] = {"get", "post", "put", "delete", "patch", "options", "head", "trace"}

    def __init__(self, raw_spec: Optional[Dict[str, Any]] = None):
        self.raw_spec: Dict[str, Any] = raw_spec or {}

    # --------------------------------------------------------------------------
    # Loader Entry Points
    # --------------------------------------------------------------------------

    @classmethod
    def load(cls, source: Union[str, Path, Dict[str, Any]]) -> APISpecification:
        """Universal loader supporting URL strings, file paths, or dictionaries."""
        if isinstance(source, dict):
            return cls.load_from_dict(source)

        str_source = str(source).strip()
        if str_source.startswith("http://") or str_source.startswith("https://"):
            return cls.load_from_url(str_source)

        return cls.load_from_file(source)

    @classmethod
    def load_from_url(cls, url: str, timeout: float = 10.0) -> APISpecification:
        """Fetch and parse OpenAPI specification from a remote HTTP/HTTPS URL."""
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.get(url)
                response.raise_for_status()
                data = response.json()
        except httpx.ConnectError as exc:
            raise SpecConnectionError(
                f"Failed to connect to API server at '{url}'. Ensure the server is running. (Error: {exc})"
            ) from exc
        except httpx.TimeoutException as exc:
            raise SpecConnectionError(
                f"Timed out after {timeout}s attempting to fetch specification from '{url}'."
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise SpecConnectionError(
                f"Server returned HTTP error {exc.response.status_code} when fetching '{url}'."
            ) from exc
        except httpx.RequestError as exc:
            raise SpecConnectionError(
                f"Network request error occurred while fetching '{url}': {exc}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise SpecParseError(
                f"Response from '{url}' was not valid JSON: {exc}"
            ) from exc

        return cls.load_from_dict(data)

    @classmethod
    def load_from_file(cls, file_path: Union[str, Path]) -> APISpecification:
        """Read and parse OpenAPI specification from a local JSON file."""
        path_obj = Path(file_path)
        if not path_obj.exists() or not path_obj.is_file():
            raise SpecNotFoundError(
                f"OpenAPI specification file not found at: {path_obj.resolve()}"
            )

        try:
            with open(path_obj, "r", encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError as exc:
            raise SpecParseError(
                f"Malformed JSON in specification file '{path_obj}': {exc}"
            ) from exc
        except UnicodeDecodeError as exc:
            raise SpecParseError(
                f"Encoding error reading specification file '{path_obj}': {exc}"
            ) from exc

        return cls.load_from_dict(data)

    @classmethod
    def load_from_dict(cls, data: Dict[str, Any]) -> APISpecification:
        """Parse an OpenAPI specification from an in-memory dictionary."""
        reader = cls(raw_spec=data)
        return reader.parse()

    # --------------------------------------------------------------------------
    # Reference Resolution Logic ($ref)
    # --------------------------------------------------------------------------

    def resolve_ref(self, ref_str: str, visited: Optional[Set[str]] = None) -> Any:
        """Resolve an internal OpenAPI JSON Pointer reference (e.g. #/components/schemas/Item)."""
        if not ref_str.startswith("#/"):
            raise SpecResolutionError(
                f"External or relative component references ('{ref_str}') are not supported. "
                "Only local document pointers ('#/') are supported."
            )

        if visited is None:
            visited = set()

        if ref_str in visited:
            # Prevent infinite recursion from circular schema definitions
            return {"$ref": ref_str, "_circular": True}

        visited.add(ref_str)

        tokens = ref_str[2:].split("/")
        current: Any = self.raw_spec

        for raw_token in tokens:
            # Unescape JSON Pointer special characters: ~1 -> /, ~0 -> ~
            token = raw_token.replace("~1", "/").replace("~0", "~")
            if not isinstance(current, dict) or token not in current:
                raise SpecResolutionError(
                    f"Component reference '{ref_str}' could not be resolved: "
                    f"token '{token}' is missing in specification."
                )
            current = current[token]

        # If the resolved target is itself a $ref, follow it recursively
        if isinstance(current, dict) and "$ref" in current:
            return self.resolve_ref(current["$ref"], visited)

        return self.resolve_schema(current, visited)

    def resolve_schema(self, schema_node: Any, visited: Optional[Set[str]] = None) -> Any:
        """Deeply resolve all $ref pointers inside a schema structure."""
        if visited is None:
            visited = set()

        if isinstance(schema_node, dict):
            if "$ref" in schema_node:
                resolved = self.resolve_ref(schema_node["$ref"], visited)
                # In OpenAPI 3.1, $ref can have sibling properties (e.g. description)
                if isinstance(resolved, dict):
                    merged = deepcopy(resolved)
                    for k, v in schema_node.items():
                        if k != "$ref":
                            merged[k] = v
                    return merged
                return resolved

            resolved_dict: Dict[str, Any] = {}
            for key, value in schema_node.items():
                resolved_dict[key] = self.resolve_schema(value, visited.copy())
            return resolved_dict

        if isinstance(schema_node, list):
            return [self.resolve_schema(item, visited.copy()) for item in schema_node]

        return schema_node

    # --------------------------------------------------------------------------
    # Main Parsing Workflow
    # --------------------------------------------------------------------------

    def parse(self) -> APISpecification:
        """Perform full validation and extraction of the OpenAPI document."""
        if not isinstance(self.raw_spec, dict):
            raise SpecValidationError("The specification must be a valid JSON/dict object.")

        openapi_version = self.raw_spec.get("openapi")
        if not openapi_version or not isinstance(openapi_version, str):
            raise SpecValidationError(
                "Missing required 'openapi' version field in specification root."
            )

        # Support OpenAPI 3.0.x and 3.1.x
        if not openapi_version.startswith("3."):
            raise SpecValidationError(
                f"Unsupported OpenAPI version '{openapi_version}'. This reader requires OpenAPI 3.x."
            )

        paths_dict = self.raw_spec.get("paths")
        if paths_dict is None or not isinstance(paths_dict, dict):
            raise SpecValidationError("Specification is missing the required 'paths' object.")

        info_dict = self.raw_spec.get("info", {})
        title = info_dict.get("title", "Untitled API")
        version = info_dict.get("version", "1.0.0")
        description = info_dict.get("description")

        # Base URL extraction
        base_url = None
        servers = self.raw_spec.get("servers", [])
        if servers and isinstance(servers, list) and isinstance(servers[0], dict):
            base_url = servers[0].get("url")

        # Security schemes
        security_schemes = self._extract_security_schemes()

        # Global security requirements
        global_security = self._extract_security_requirements(self.raw_spec.get("security", []))

        # Endpoints & Operations
        endpoints: List[str] = list(paths_dict.keys())
        operations: List[OperationDefinition] = []

        for path, path_item in paths_dict.items():
            if not isinstance(path_item, dict):
                continue
            path_ops = self._parse_path_item(path, path_item, global_security)
            operations.extend(path_ops)

        return APISpecification(
            title=title,
            version=version,
            openapi_version=openapi_version,
            description=description,
            base_url=base_url,
            endpoints=endpoints,
            operations=operations,
            security_schemes=security_schemes,
            global_security=global_security,
            components=self.raw_spec.get("components", {}),
            raw_spec=self.raw_spec,
        )

    # --------------------------------------------------------------------------
    # Sub-component Parsers
    # --------------------------------------------------------------------------

    def _extract_security_schemes(self) -> Dict[str, SecuritySchemeDefinition]:
        """Extract and structure security schemes declared in components."""
        schemes_dict: Dict[str, SecuritySchemeDefinition] = {}
        raw_components = self.raw_spec.get("components", {})
        raw_schemes = raw_components.get("securitySchemes", {})

        if not isinstance(raw_schemes, dict):
            return schemes_dict

        for name, scheme_data in raw_schemes.items():
            if isinstance(scheme_data, dict):
                if "$ref" in scheme_data:
                    scheme_data = self.resolve_ref(scheme_data["$ref"])

                schemes_dict[name] = SecuritySchemeDefinition(
                    name=name,
                    type=scheme_data.get("type", "unknown"),
                    scheme=scheme_data.get("scheme"),
                    bearer_format=scheme_data.get("bearerFormat"),
                    location=scheme_data.get("in"),
                    parameter_name=scheme_data.get("name"),
                    description=scheme_data.get("description"),
                )

        return schemes_dict

    def _extract_security_requirements(self, sec_list: Any) -> List[SecurityRequirement]:
        """Extract security requirements list."""
        requirements: List[SecurityRequirement] = []
        if not isinstance(sec_list, list):
            return requirements

        for req_dict in sec_list:
            if isinstance(req_dict, dict):
                for scheme_name, scopes in req_dict.items():
                    requirements.append(
                        SecurityRequirement(
                            scheme_name=scheme_name,
                            scopes=scopes if isinstance(scopes, list) else [],
                        )
                    )
        return requirements

    def _parse_path_item(
        self,
        path: str,
        path_item: Dict[str, Any],
        global_security: List[SecurityRequirement],
    ) -> List[OperationDefinition]:
        """Extract all operations from a path item, merging path-level parameters."""
        operations: List[OperationDefinition] = []

        # Common parameters defined at the path item level
        common_params = self._parse_parameters(path_item.get("parameters", []))

        for method, op_data in path_item.items():
            method_lower = method.lower()
            if method_lower not in self.HTTP_METHODS or not isinstance(op_data, dict):
                continue

            # Merge operation-level parameters with common parameters
            op_params = self._parse_parameters(op_data.get("parameters", []))
            merged_params = self._merge_parameters(common_params, op_params)

            # Request body
            request_body = self._parse_request_body(op_data.get("requestBody"))

            # Responses and links
            responses, links = self._parse_responses(op_data.get("responses", {}))

            # Security: If operation specifies 'security', it overrides global
            if "security" in op_data:
                op_security = self._extract_security_requirements(op_data.get("security", []))
            else:
                op_security = list(global_security)

            operations.append(
                OperationDefinition(
                    operation_id=op_data.get("operationId"),
                    method=method.upper(),
                    path=path,
                    summary=op_data.get("summary"),
                    description=op_data.get("description"),
                    tags=op_data.get("tags", []),
                    parameters=merged_params,
                    request_body=request_body,
                    responses=responses,
                    security=op_security,
                    links=links,
                )
            )

        return operations

    def _parse_parameters(self, raw_params: Any) -> List[ParameterDefinition]:
        """Parse parameter definitions, resolving references when necessary."""
        params: List[ParameterDefinition] = []
        if not isinstance(raw_params, list):
            return params

        for param_node in raw_params:
            if not isinstance(param_node, dict):
                continue

            if "$ref" in param_node:
                param_node = self.resolve_ref(param_node["$ref"])

            name = param_node.get("name")
            location = param_node.get("in")
            if not name or not location:
                continue

            schema_info = None
            if "schema" in param_node:
                schema_info = self.resolve_schema(param_node["schema"])

            # In OpenAPI, path parameters are always required
            required = param_node.get("required", location == "path")

            params.append(
                ParameterDefinition(
                    name=name,
                    location=location,
                    required=required,
                    description=param_node.get("description"),
                    schema_info=schema_info,
                )
            )

        return params

    def _merge_parameters(
        self,
        common_params: List[ParameterDefinition],
        op_params: List[ParameterDefinition],
    ) -> List[ParameterDefinition]:
        """Merge path-level and operation-level parameters (operation overrides matching (name, location))."""
        merged_dict: Dict[tuple[str, str], ParameterDefinition] = {
            (p.name, p.location): p for p in common_params
        }
        for p in op_params:
            merged_dict[(p.name, p.location)] = p
        return list(merged_dict.values())

    def _parse_request_body(self, raw_body: Any) -> Optional[RequestBodyDefinition]:
        """Parse requestBody object, extracting supported media types and resolved schemas."""
        if not raw_body or not isinstance(raw_body, dict):
            return None

        if "$ref" in raw_body:
            raw_body = self.resolve_ref(raw_body["$ref"])

        content = raw_body.get("content", {})
        content_types: List[str] = []
        schemas: Dict[str, Dict[str, Any]] = {}

        if isinstance(content, dict):
            for media_type, media_obj in content.items():
                content_types.append(media_type)
                if isinstance(media_obj, dict) and "schema" in media_obj:
                    schemas[media_type] = self.resolve_schema(media_obj["schema"])

        return RequestBodyDefinition(
            required=raw_body.get("required", False),
            description=raw_body.get("description"),
            content_types=content_types,
            schemas=schemas,
        )

    def _parse_responses(
        self,
        raw_responses: Any,
    ) -> tuple[Dict[str, ResponseDefinition], Dict[str, Dict[str, Any]]]:
        """Parse documented responses and extract explicit OpenAPI links."""
        responses: Dict[str, ResponseDefinition] = {}
        all_links: Dict[str, Dict[str, Any]] = {}

        if not isinstance(raw_responses, dict):
            return responses, all_links

        for status_code, resp_node in raw_responses.items():
            if not isinstance(resp_node, dict):
                continue

            if "$ref" in resp_node:
                resp_node = self.resolve_ref(resp_node["$ref"])

            content = resp_node.get("content", {})
            content_types: List[str] = []
            schemas: Dict[str, Dict[str, Any]] = {}

            if isinstance(content, dict):
                for media_type, media_obj in content.items():
                    content_types.append(media_type)
                    if isinstance(media_obj, dict) and "schema" in media_obj:
                        schemas[media_type] = self.resolve_schema(media_obj["schema"])

            # Explicit OpenAPI response links (dependencies)
            links = resp_node.get("links", {})
            resolved_links: Dict[str, Dict[str, Any]] = {}
            if isinstance(links, dict):
                for link_name, link_obj in links.items():
                    if isinstance(link_obj, dict):
                        if "$ref" in link_obj:
                            link_obj = self.resolve_ref(link_obj["$ref"])
                        resolved_links[link_name] = link_obj
                        all_links[f"{status_code}.{link_name}"] = link_obj

            responses[str(status_code)] = ResponseDefinition(
                status_code=str(status_code),
                description=resp_node.get("description"),
                content_types=content_types,
                schemas=schemas,
                links=resolved_links,
            )

        return responses, all_links


# ------------------------------------------------------------------------------
# Quick CLI Interface for Testing & Inspection
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/openapi.json"
    print(f"\n--- Reading OpenAPI Specification: {target} ---")
    try:
        spec = OpenAPISpecReader.load(target)
        print(f"Title: {spec.title}")
        print(f"Version: {spec.version} (OpenAPI {spec.openapi_version})")
        print(f"Discovered Endpoints ({len(spec.endpoints)}): {', '.join(spec.endpoints)}")
        print(f"Discovered Operations ({len(spec.operations)}):")
        for op in spec.operations:
            auth_status = "AUTH" if op.security else "PUBLIC"
            params_str = f"Params: {[p.name for p in op.parameters]}" if op.parameters else "No params"
            body_str = f"Body: {op.request_body.content_types}" if op.request_body else "No body"
            resp_str = f"Responses: {list(op.responses.keys())}"
            print(f"  * {op.method:<6} {op.path:<24} [{auth_status:<6}] | {params_str} | {body_str} | {resp_str}")
        print(f"Security Schemes: {list(spec.security_schemes.keys())}")
        print("\nSpecification successfully parsed and validated!\n")
    except SpecReaderError as err:
        print(f"Specification Error: {err}", file=sys.stderr)
        sys.exit(1)
