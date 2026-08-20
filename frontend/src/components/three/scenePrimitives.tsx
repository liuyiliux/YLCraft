/**
 * YLCraft — 可复用 3D 场景渲染原语
 *
 * 从 Model3DViewer 提取的纯渲染能力，供通用查看器与 3D 导演预演台共用。
 * 这里只放无业务状态的底层原语（渲染模式、包围盒、模型元数据、部位树、
 * 材质辅助），不承载 Story 分镜、节点 transform、锁定、相机或关键帧等业务状态。
 */

import { useEffect, useMemo } from 'react'
import * as THREE from 'three'

export type RenderMode = 'texture' | 'white' | 'wireframe' | 'albedo' | 'normal'

export interface Asset3DMetadata {
  format: string
  fileSize: number
  vertices: number
  faces: number
  materials: number
  textures: string[]
  hasAnimation: boolean
  boundingBox: {
    width: number
    height: number
    depth: number
  }
}

// 模型部位树节点（腾讯 Hunyuan Studio 风格的部位拆分，基于骨骼层级）
export interface PartNode {
  name: string
  path: string
  childCount?: number
  children?: PartNode[]
}

// 计算模型元数据（GLB/GLTF 与 OBJ 共用）
export function computeModelMetadata(object: THREE.Object3D, format: string): Asset3DMetadata {
  const box = new THREE.Box3().setFromObject(object)
  const size = box.getSize(new THREE.Vector3())

  let vertices = 0
  let faces = 0
  object.traverse((child) => {
    if (child instanceof THREE.Mesh) {
      const geometry = child.geometry
      if (geometry.index) faces += geometry.index.count / 3
      else if (geometry.attributes.position) faces += geometry.attributes.position.count / 3
      vertices += geometry.attributes.position?.count || 0
    }
  })

  const materialNames = new Set<string>()
  const textureKinds = new Set<string>()
  object.traverse((child) => {
    if (child instanceof THREE.Mesh) {
      const mats = Array.isArray(child.material) ? child.material : [child.material]
      mats.filter(Boolean).forEach((m) => {
        materialNames.add(m.name || 'material')
        if (m.map) textureKinds.add('diffuse')
        if (m.normalMap) textureKinds.add('normal')
        if (m.roughnessMap) textureKinds.add('roughness')
        if (m.metalnessMap) textureKinds.add('metalness')
      })
    }
  })

  let hasAnimation = false
  object.traverse((child) => {
    if ((child as any).animation) hasAnimation = true
  })

  return {
    format,
    fileSize: 0,
    vertices,
    faces: Math.round(faces),
    materials: materialNames.size || 1,
    textures: [...textureKinds],
    hasAnimation,
    boundingBox: { width: size.x, height: size.y, depth: size.z },
  }
}

export function computeModelBox(object: THREE.Object3D): { center: THREE.Vector3; size: THREE.Vector3 } {
  const box = new THREE.Box3().setFromObject(object)
  const center = new THREE.Vector3()
  const size = new THREE.Vector3()
  box.getCenter(center)
  box.getSize(size)
  return { center, size }
}

export function firstMap(material: THREE.Material | THREE.Material[]): THREE.Texture | null {
  const mats = Array.isArray(material) ? material : [material]
  for (const m of mats) {
    const anyM = m as any
    if (anyM.map) return anyM.map
  }
  return null
}

export function firstNormalMap(material: THREE.Material | THREE.Material[]): THREE.Texture | null {
  const mats = Array.isArray(material) ? material : [material]
  for (const m of mats) {
    const anyM = m as any
    if (anyM.normalMap) return anyM.normalMap
    if (anyM.bumpMap) return anyM.bumpMap
  }
  return null
}

// 每个 mesh 的原始材质（模块级 WeakMap：useGLTF 会按 URL 缓存并复用同一场景，
// 若用组件内 ref 记录，切过白模/反照率后重开模型会把被覆盖的材质误当原始材质）。
const ORIGINAL_MATERIALS = new WeakMap<THREE.Mesh, THREE.Material | THREE.Material[]>()

// 渲染模式：切换材质覆盖（保留原始材质以便恢复纹理模式）
export function useRenderMode(object: THREE.Object3D | null, mode: RenderMode) {
  useEffect(() => {
    if (!object) return
    object.traverse((child) => {
      if (child instanceof THREE.Mesh) {
        if (!ORIGINAL_MATERIALS.has(child)) ORIGINAL_MATERIALS.set(child, child.material)
        const original = ORIGINAL_MATERIALS.get(child)!
        if (mode === 'texture') {
          child.material = original
        } else if (mode === 'white') {
          child.material = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.85, metalness: 0.05 })
        } else if (mode === 'wireframe') {
          child.material = new THREE.MeshStandardMaterial({ color: 0xffffff, wireframe: true })
        } else if (mode === 'albedo') {
          const map = firstMap(original)
          child.material = new THREE.MeshBasicMaterial({ map: map || undefined, color: map ? 0xffffff : 0xd4d4d8, side: THREE.DoubleSide })
        } else if (mode === 'normal') {
          const map = firstNormalMap(original)
          child.material = new THREE.MeshBasicMaterial({ map: map || undefined, color: map ? 0xffffff : 0x8080ff, side: THREE.DoubleSide })
        }
      }
    })
  }, [object, mode])
}

// 白色线框包围盒
export function BoundingBox({ object }: { object: THREE.Object3D }) {
  const box = useMemo(() => {
    const b = new THREE.Box3().setFromObject(object)
    const size = new THREE.Vector3()
    const center = new THREE.Vector3()
    b.getSize(size)
    b.getCenter(center)
    return { size, center }
  }, [object])
  return (
    <lineSegments position={[box.center.x, box.center.y, box.center.z]}>
      <edgesGeometry args={[new THREE.BoxGeometry(box.size.x, box.size.y, box.size.z)]} />
      <lineBasicMaterial color="#ffffff" transparent opacity={0.7} />
    </lineSegments>
  )
}

// ==================== 部位树（骨骼层级）====================
// 腾讯 Hunyuan Studio 风格的部位拆分：以骨骼层级为树，把网格按
// skinWeight 最大权重归属到骨骼节点，实现"隐藏/显示某个肢体部位"。

type BoneNode = { bone: THREE.Bone; name: string; children: BoneNode[]; meshes: number }

export function countMeshes(obj: THREE.Object3D): number {
  let n = 0
  obj.traverse(child => { if (child instanceof THREE.Mesh) n++ })
  return n
}

export function meshPrimaryBone(mesh: THREE.SkinnedMesh): THREE.Bone | null {
  const geom = mesh.geometry as THREE.BufferGeometry
  const si = geom.attributes.skinIndex as THREE.BufferAttribute | undefined
  const sw = geom.attributes.skinWeight as THREE.BufferAttribute | undefined
  if (!si || !sw || !mesh.skeleton?.bones?.length) return null
  const skeleton = mesh.skeleton
  const counts = new Map<number, number>()
  const n = si.count
  for (let i = 0; i < n; i++) {
    let maxW = -Infinity
    let maxB = -1
    for (let j = 0; j < 4; j++) {
      const w = sw.array[i * 4 + j] as number
      if (w > maxW) {
        maxW = w
        maxB = si.array[i * 4 + j] as number
      }
    }
    if (maxB >= 0 && maxB < skeleton.bones.length) {
      counts.set(maxB, (counts.get(maxB) || 0) + 1)
    }
  }
  let best: THREE.Bone | null = null
  let bestCount = 0
  counts.forEach((count, index) => {
    if (count > bestCount) {
      bestCount = count
      best = skeleton.bones[index]
    }
  })
  return best
}

// 骨骼在骨骼树中的路径（只含 bone 链，与 buildPartTree 的 path 一致）
export function primaryBonePath(mesh: THREE.SkinnedMesh): string | null {
  const bone = meshPrimaryBone(mesh)
  if (!bone) return null
  const parts: string[] = []
  let current: THREE.Object3D | null = bone
  while (current instanceof THREE.Bone) {
    parts.unshift(current.name || 'bone')
    current = current.parent
  }
  return parts.join('/')
}

export function buildPartTree(scene: THREE.Object3D): PartNode[] {
  const map = new Map<THREE.Bone, BoneNode>()
  const roots: THREE.Bone[] = []
  scene.traverse(obj => {
    if (obj instanceof THREE.SkinnedMesh) {
      obj.skeleton.bones.forEach(bone => {
        if (!map.has(bone)) {
          map.set(bone, { bone, name: bone.name || 'bone', children: [], meshes: 0 })
        }
      })
    }
  })

  // 无骨骼模型：退化为 scene 直接子节点（mesh/group）作为部位
  if (map.size === 0) {
    const nodes: PartNode[] = []
    scene.children.forEach(child => {
      if (child instanceof THREE.Mesh || child instanceof THREE.Group) {
        nodes.push({ name: child.name || child.type, path: child.name || child.uuid, childCount: child instanceof THREE.Mesh ? 1 : countMeshes(child) })
      }
    })
    return nodes
  }

  // 建立骨骼树：向上找最近的骨骼父节点
  map.forEach((node, bone) => {
    let parent: THREE.Object3D | null = bone.parent
    while (parent && !(parent instanceof THREE.Bone)) parent = parent.parent
    if (parent && map.has(parent as THREE.Bone)) {
      map.get(parent as THREE.Bone)!.children.push(node)
    } else {
      roots.push(bone)
    }
  })

  // 网格归属计数：每个 SkinnedMesh 计入其主骨骼
  scene.traverse(obj => {
    if (obj instanceof THREE.SkinnedMesh) {
      const primary = meshPrimaryBone(obj)
      if (primary && map.has(primary)) map.get(primary)!.meshes += 1
    }
  })

  const convert = (bone: THREE.Bone, parentPath: string): PartNode => {
    const node = map.get(bone)!
    const path = parentPath ? `${parentPath}/${node.name}` : node.name
    return {
      name: node.name,
      path,
      childCount: node.meshes,
      children: node.children.length ? node.children.map(child => convert(child.bone, path)) : undefined,
    }
  }
  return roots.map(bone => convert(bone, ''))
}
