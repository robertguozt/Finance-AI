using UnityEngine;

namespace BirdCombat.Birds
{
    public abstract class BirdAbility : MonoBehaviour
    {
        [SerializeField] private string displayName = "Ability";
        [SerializeField] private float cooldown = 8f;
        [SerializeField] private float staminaCost = 20f;

        protected BirdController Owner { get; private set; }
        protected float LastUseTime { get; private set; } = float.NegativeInfinity;

        public void Initialize(BirdController owner)
        {
            Owner = owner;
        }

        public bool TryExecute()
        {
            if (!CanUse())
                return false;

            if (Owner != null && !Owner.TryConsumeStamina(staminaCost))
                return false;

            Execute();
            LastUseTime = Time.time;
            return true;
        }

        protected virtual bool CanUse()
        {
            return Owner != null && Owner.IsAlive && Time.time >= LastUseTime + cooldown && Owner.HasStamina(staminaCost);
        }

        protected abstract void Execute();

        public virtual string DisplayName => displayName;
        public float Cooldown => cooldown;
        public float StaminaCost => staminaCost;
    }
}
