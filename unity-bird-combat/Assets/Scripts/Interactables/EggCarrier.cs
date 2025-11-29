using UnityEngine;

namespace BirdCombat.Interactables
{
    public class EggCarrier : MonoBehaviour
    {
        [SerializeField] private Transform eggVisualAnchor;
        [SerializeField] private GameObject eggVisualPrefab;

        private NestController originNest;
        private GameObject activeVisual;
        private BirdCombat.Birds.BirdController owner;

        private void Awake()
        {
            owner = GetComponent<BirdCombat.Birds.BirdController>();
        }

        public bool HasEgg => originNest != null;
        public NestController OriginNest => originNest;

        public void AttachEgg(NestController nest)
        {
            originNest = nest;
            SpawnVisual();
        }

        public void CaptureEgg(NestController friendlyNest)
        {
            if (!HasEgg)
                return;

            friendlyNest?.NotifyEggCaptured(owner, originNest);
            originNest = null;
            DestroyVisual();
        }

        public void DropEgg(bool dueToDeath)
        {
            if (!HasEgg)
                return;

            originNest?.ReturnEgg();
            originNest = null;
            DestroyVisual();
        }

        private void SpawnVisual()
        {
            if (eggVisualPrefab == null || eggVisualAnchor == null || activeVisual != null)
                return;

            activeVisual = Object.Instantiate(eggVisualPrefab, eggVisualAnchor);
            activeVisual.transform.localPosition = Vector3.zero;
            activeVisual.transform.localRotation = Quaternion.identity;
        }

        private void DestroyVisual()
        {
            if (activeVisual != null)
            {
                Object.Destroy(activeVisual);
                activeVisual = null;
            }
        }
    }
}
