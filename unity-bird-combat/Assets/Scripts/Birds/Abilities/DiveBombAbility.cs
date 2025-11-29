using UnityEngine;
using BirdCombat.Combat;

namespace BirdCombat.Birds.Abilities
{
    public class DiveBombAbility : BirdAbility
    {
        [SerializeField] private float diveForce = 40f;
        [SerializeField] private float damageRadius = 5f;
        [SerializeField] private float baseDamage = 60f;
        [SerializeField] private AnimationCurve falloff = AnimationCurve.EaseInOut(0, 1, 1, 0);

        protected override void Execute()
        {
            if (Owner == null)
                return;

            Owner.AddImpulse((Owner.transform.forward + Vector3.down * 0.75f).normalized * diveForce);
            DamageSystem.ApplyAreaDamage(Owner.transform.position, damageRadius, baseDamage, falloff, Owner);
        }
    }
}
