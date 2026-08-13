# Design

- A connector has explicit `provider_type: "3d"`; endpoint names never imply capability.
- Connector request/response configuration describes JSON request rendering, task ID/status/model URL JSONPaths and an optional polling endpoint.
- `/api/v1/model-3d` owns standalone backend discovery, submit, poll and durable history.
- Completed model URLs download locally, then create `AssetNode(3d_model) -> AssetVersion -> AssetRepresentation` exactly once. When the input was an Asset Hub image, an `AssetRelation(derived_from)` records lineage.
- The existing `/api/v1/3d` TripoSR and utility routes stay compatible but are not extended by this workspace.
- GLB is the default expected output. Format conversion and server-rendered preview remain out of scope until a real conversion/rendering backend exists.
