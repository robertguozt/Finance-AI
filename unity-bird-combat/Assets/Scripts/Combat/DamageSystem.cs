using UnityEngine;
using BirdCombat.Birds;

namespace BirdCombat.Combat
{
    public static class DamageSystem
    {
        private static readonly int BirdLayer = LayerMask.NameToLayer("Bird");

        public static void ApplyAreaDamage(Vector3 position, float radius, float baseDamage, AnimationCurve falloff, BirdController instigator)
        {
            var colliders = Physics.OverlapSphere(position, radius);
            foreach (var collider in colliders)
            {
                if (!collider.TryGetComponent(out BirdController target) || target == instigator)
                    continue;

                float distance = Vector3.Distance(position, target.transform.position);
                float normalized = Mathf.Clamp01(distance / radius);
                float multiplier = falloff != null ? falloff.Evaluate(normalized) : 1f - normalized;
                target.ApplyDamage(baseDamage * multiplier, instigator);
            }
        }
    }
}
