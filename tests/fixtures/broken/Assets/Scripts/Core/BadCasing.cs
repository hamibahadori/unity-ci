namespace Wrong.Namespace
{
    public class BadCasing
    {
        private int BadField = 1;

        public void badMethod(int X)
        {
            int q = X;
            BadField = q;
        }

        public bool IsMissing(object candidate)
        {
            return candidate is null;
        }
    }
}
