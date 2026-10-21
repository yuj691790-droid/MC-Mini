import java.io.File;

/** Calls the upstream installer's public API; no OptiFine code is included. */
public final class OptiFineBridge {
    public static void main(String[] args) throws Exception {
        Class.forName("optifine.Installer")
            .getMethod("doInstall", File.class)
            .invoke(null, new File(args[0]));
    }
}
