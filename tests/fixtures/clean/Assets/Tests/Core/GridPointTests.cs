using NUnit.Framework;

namespace Game.Core.Tests
{
    public class GridPointTests
    {
        [Test]
        public void Equality_SameCoordinates_IsTrue()
        {
            // Underscored method names are the convention in a .Tests assembly, and must not be
            // flagged here while still being flagged everywhere else.
            Assert.IsTrue(new GridPoint(1, 2) == new GridPoint(1, 2));
        }
    }
}
