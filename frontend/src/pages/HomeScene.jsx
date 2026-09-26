import { useEffect, useRef } from 'react'
import * as THREE from 'three'

function makeRibbon(points, color, radius = 0.095) {
  const curve = new THREE.CatmullRomCurve3(
    points.map(([x, y, z]) => new THREE.Vector3(x, y, z)),
    false,
    'catmullrom',
    0.55,
  )
  return new THREE.Mesh(
    new THREE.TubeGeometry(curve, 140, radius, 14, false),
    new THREE.MeshPhysicalMaterial({
      color,
      metalness: 0.08,
      roughness: 0.2,
      clearcoat: 1,
      clearcoatRoughness: 0.18,
    }),
  )
}

export default function HomeScene() {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const host = canvas?.parentElement
    if (!canvas || !host) return undefined

    const scene = new THREE.Scene()
    scene.fog = new THREE.FogExp2(0x071619, 0.065)
    const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 100)
    camera.position.set(0, 0, 9)

    const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true })
    renderer.setClearColor(0x071619, 0)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75))
    renderer.outputColorSpace = THREE.SRGBColorSpace

    const sculpture = new THREE.Group()
    sculpture.position.set(1.65, -0.05, 0)
    sculpture.rotation.set(-0.04, -0.16, 0.03)
    scene.add(sculpture)

    const left = makeRibbon([
      [-2.1, -2.55, 0], [-1.65, -1.2, 0.35], [-0.85, 0.55, -0.25],
      [0, 2.45, 0.15], [0.6, 1.15, 0.5], [1.4, -0.75, -0.15], [2.1, -2.55, 0.2],
    ], 0xd4eee8, 0.12)
    sculpture.add(left)

    const weave = makeRibbon([
      [-1.95, -0.55, -0.05], [-1.1, -0.15, 0.55], [-0.25, 0.08, 0.15],
      [0.65, -0.08, -0.5], [1.75, -0.48, 0.1], [0.8, -0.78, 0.52],
      [-0.25, -0.88, -0.1], [-1.25, -0.82, -0.45], [-1.95, -0.55, -0.05],
    ], 0xe26c50, 0.085)
    sculpture.add(weave)

    const signal = makeRibbon([
      [-1.25, -2.25, -0.35], [-0.8, -1.05, -0.55], [-0.05, 0.25, 0.45],
      [0.1, 1.75, -0.25], [-0.7, 2.05, -0.55], [-1.15, 1.4, 0.2],
    ], 0xd7ae59, 0.048)
    sculpture.add(signal)

    const halo = new THREE.Mesh(
      new THREE.TorusGeometry(2.75, 0.012, 8, 160),
      new THREE.MeshBasicMaterial({ color: 0x6ea9a2, transparent: true, opacity: 0.28 }),
    )
    halo.rotation.set(1.15, 0.15, 0.2)
    sculpture.add(halo)

    const nodeGeometry = new THREE.SphereGeometry(0.055, 16, 16)
    const nodeMaterial = new THREE.MeshBasicMaterial({ color: 0xf2c970 })
    const nodes = [
      [-1.65, -1.2, 0.35], [0, 2.45, 0.15], [1.4, -0.75, -0.15],
      [-0.25, 0.08, 0.15], [0.8, -0.78, 0.52],
    ].map((position) => {
      const node = new THREE.Mesh(nodeGeometry, nodeMaterial)
      node.position.set(...position)
      sculpture.add(node)
      return node
    })

    const dustGeometry = new THREE.BufferGeometry()
    const dustPositions = new Float32Array(150 * 3)
    for (let index = 0; index < 150; index += 1) {
      dustPositions[index * 3] = (Math.random() - 0.5) * 8
      dustPositions[index * 3 + 1] = (Math.random() - 0.5) * 7
      dustPositions[index * 3 + 2] = (Math.random() - 0.5) * 3
    }
    dustGeometry.setAttribute('position', new THREE.BufferAttribute(dustPositions, 3))
    const dust = new THREE.Points(
      dustGeometry,
      new THREE.PointsMaterial({ color: 0x90c2bb, size: 0.018, transparent: true, opacity: 0.38 }),
    )
    sculpture.add(dust)

    scene.add(new THREE.HemisphereLight(0xcdf7ef, 0x071619, 2.1))
    const coralLight = new THREE.PointLight(0xe26c50, 28, 12)
    coralLight.position.set(3, -1.5, 4)
    const tealLight = new THREE.PointLight(0x5dcabd, 24, 12)
    tealLight.position.set(-2, 2.5, 3)
    scene.add(coralLight, tealLight)

    const pointer = { x: 0, y: 0 }
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const onPointerMove = (event) => {
      pointer.x = (event.clientX / window.innerWidth - 0.5) * 0.42
      pointer.y = (event.clientY / window.innerHeight - 0.5) * 0.24
    }
    window.addEventListener('pointermove', onPointerMove, { passive: true })

    const resize = () => {
      const { width, height } = host.getBoundingClientRect()
      renderer.setSize(width, height, false)
      camera.aspect = width / height
      camera.updateProjectionMatrix()
      sculpture.position.x = width < 760 ? 0 : 1.65
      sculpture.scale.setScalar(width < 760 ? 0.78 : 1)
    }
    const observer = new ResizeObserver(resize)
    observer.observe(host)
    resize()

    const startedAt = performance.now()
    let frameId
    const draw = () => {
      const elapsed = (performance.now() - startedAt) / 1000
      if (!reduceMotion) {
        sculpture.rotation.y += (pointer.x - sculpture.rotation.y) * 0.022
        sculpture.rotation.x += (-pointer.y - sculpture.rotation.x) * 0.022
        sculpture.position.y = Math.sin(elapsed * 0.42) * 0.08
        weave.rotation.z = Math.sin(elapsed * 0.34) * 0.035
        halo.rotation.z = elapsed * 0.035
        dust.rotation.y = elapsed * 0.018
        nodes.forEach((node, index) => node.scale.setScalar(1 + Math.sin(elapsed * 1.7 + index) * 0.28))
      }
      renderer.render(scene, camera)
      frameId = window.requestAnimationFrame(draw)
    }
    draw()

    return () => {
      window.cancelAnimationFrame(frameId)
      window.removeEventListener('pointermove', onPointerMove)
      observer.disconnect()
      scene.traverse((object) => {
        object.geometry?.dispose()
        if (Array.isArray(object.material)) object.material.forEach((material) => material.dispose())
        else object.material?.dispose()
      })
      renderer.dispose()
    }
  }, [])

  return <canvas ref={canvasRef} className="home-scene" aria-hidden="true" />
}
