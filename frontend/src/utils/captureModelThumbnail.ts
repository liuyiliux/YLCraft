import * as THREE from 'three'
import { GLTFLoader, OBJLoader, MTLLoader } from 'three-stdlib'

/**
 * 用离屏 WebGL 渲染一个 3D 模型并返回 PNG data URL，用于生成素材缩略图。
 */
export function captureModelThumbnail(
  modelUrl: string,
  mtlUrl?: string,
  size = 512,
): Promise<string> {
  return new Promise((resolve, reject) => {
    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      preserveDrawingBuffer: true,
      alpha: true,
    })
    renderer.setSize(size, size)
    renderer.setClearColor(0x16161a, 1)

    const scene = new THREE.Scene()
    scene.add(new THREE.AmbientLight(0xffffff, 0.7))
    const key = new THREE.DirectionalLight(0xffffff, 1.1)
    key.position.set(3, 5, 4)
    scene.add(key)
    const fill = new THREE.DirectionalLight(0xffffff, 0.35)
    fill.position.set(-3, 2, -2)
    scene.add(fill)

    const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 100)
    camera.position.set(0, 1.2, 5.5)
    camera.lookAt(0, 0.4, 0)

    const fit = (object: THREE.Object3D) => {
      const box = new THREE.Box3().setFromObject(object)
      const center = box.getCenter(new THREE.Vector3())
      const sizeVec = box.getSize(new THREE.Vector3())
      const maxDim = Math.max(sizeVec.x, sizeVec.y, sizeVec.z, 0.0001)
      object.position.sub(center)
      object.scale.setScalar(2.2 / maxDim)
      const fitted = new THREE.Box3().setFromObject(object)
      object.position.y -= fitted.min.y
      scene.add(object)

      renderer.render(scene, camera)
      const dataUrl = renderer.domElement.toDataURL('image/png')
      renderer.dispose()
      resolve(dataUrl)
    }

    if (modelUrl.toLowerCase().endsWith('.obj') && mtlUrl) {
      const mtlLoader = new MTLLoader()
      mtlLoader.load(
        mtlUrl,
        (materials) => {
          materials.preload()
          const objLoader = new OBJLoader()
          objLoader.setMaterials(materials)
          objLoader.load(modelUrl, fit, undefined, reject)
        },
        undefined,
        reject,
      )
    } else {
      const gltfLoader = new GLTFLoader()
      gltfLoader.load(modelUrl, (gltf) => fit(gltf.scene), undefined, reject)
    }
  })
}
