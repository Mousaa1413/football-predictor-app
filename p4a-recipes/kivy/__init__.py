"""Local kivy recipe: block host SDL2 pkg-config flags during Android cross-build.

Root cause (build_log):
  When building kivy==2.3.x for Android, setup.py still runs:
      pkg-config --cflags --libs sdl2 SDL2_ttf SDL2_image SDL2_mixer
  even though platform=android and KIVY_SDL2_PATH already points at the
  p4a/bootstrap SDL headers. With host libsdl2-dev installed (common in
  Buildozer CI images), that injects:

      -I/usr/include/SDL2 -I/usr/include/x86_64-linux-gnu ...

  into the NDK clang command. NDK's alloca.h then pulls host
  /usr/include/x86_64-linux-gnu/sys/cdefs.h and fails with:

      error: function-like macro '__GNUC_PREREQ' is not defined

Fix:
  - Keep upstream recipe behaviour (USE_SDL2, KIVY_SDL2_PATH, patches).
  - Force pkg-config to see no host .pc files for this recipe only.
  - Always set KIVY_CROSS_PLATFORM=android (upstream only does this for kivy>=3).
"""
from os.path import join
import sys
import packaging.version

import sh
from pythonforandroid.recipe import PyProjectRecipe
from pythonforandroid.toolchain import current_directory, shprint


def get_kivy_version(recipe, arch):
    with current_directory(join(recipe.get_build_dir(arch.arch), "kivy")):
        return shprint(
            sh.Command(sys.executable),
            "-c",
            "import _version; print(_version.__version__)",
        )


def is_kivy_affected_by_deadlock_issue(recipe=None, arch=None):
    return packaging.version.parse(
        str(get_kivy_version(recipe, arch))
    ) < packaging.version.Version("2.2.0.dev0")


def is_kivy_less_than_3(recipe=None, arch=None):
    return packaging.version.parse(
        str(get_kivy_version(recipe, arch))
    ) < packaging.version.Version("3.0.0.dev0")


class KivyRecipe(PyProjectRecipe):
    # Default matches upstream; buildozer.spec may still pin kivy==2.3.0.
    version = "2.3.1"
    url = "https://github.com/kivy/kivy/archive/{version}.zip"
    name = "kivy"

    depends = [("sdl2", "sdl3"), "pyjnius", "setuptools", "android"]
    python_depends = ["certifi", "chardet", "idna", "requests", "urllib3", "filetype"]
    hostpython_prerequisites = ["cython>=0.29.1,<=3.0.12"]

    patches = [
        ("sdl-gl-swapwindow-nogil.patch", is_kivy_affected_by_deadlock_issue),
        ("use_cython.patch", is_kivy_less_than_3),
        "no-ast-str.patch",
    ]

    @property
    def need_stl_shared(self):
        return "sdl3" in self.ctx.recipe_build_order

    def get_recipe_env(self, arch, **kwargs):
        env = super().get_recipe_env(arch, **kwargs)

        env["LDFLAGS"] = env["LDFLAGS"] + " -L{} ".format(
            self.ctx.get_libs_dir(arch.arch)
            + " -L{} ".format(self.ctx.libs_dir)
            + " -L{}".format(
                join(self.ctx.bootstrap.build_dir, "obj", "local", arch.arch)
            )
        )
        env["LDSHARED"] = env["CC"] + " -shared"
        env["LIBLINK"] = "NOTNONE"

        # NDKPLATFORM is kivy's switch for detecting Android (with LIBLINK).
        env["NDKPLATFORM"] = "NOTNONE"
        # Upstream only sets this for kivy >= 3; set always for correct paths.
        env["KIVY_CROSS_PLATFORM"] = "android"

        # Critical: do not let host libsdl2.pc cflags leak into NDK compile.
        # Empty LIBDIR makes pkg-config ignore the default system search path.
        env["PKG_CONFIG_PATH"] = ""
        env["PKG_CONFIG_LIBDIR"] = ""

        if "sdl2" in self.ctx.recipe_build_order:
            env["USE_SDL2"] = "1"
            env["KIVY_SPLIT_EXAMPLES"] = "1"
            sdl2_mixer_recipe = self.get_recipe("sdl2_mixer", self.ctx)
            sdl2_image_recipe = self.get_recipe("sdl2_image", self.ctx)
            env["KIVY_SDL2_PATH"] = ":".join(
                [
                    join(self.ctx.bootstrap.build_dir, "jni", "SDL", "include"),
                    *sdl2_image_recipe.get_include_dirs(arch),
                    *sdl2_mixer_recipe.get_include_dirs(arch),
                    join(self.ctx.bootstrap.build_dir, "jni", "SDL2_ttf"),
                ]
            )

        if "sdl3" in self.ctx.recipe_build_order:
            sdl3_mixer_recipe = self.get_recipe("sdl3_mixer", self.ctx)
            sdl3_image_recipe = self.get_recipe("sdl3_image", self.ctx)
            sdl3_ttf_recipe = self.get_recipe("sdl3_ttf", self.ctx)
            sdl3_recipe = self.get_recipe("sdl3", self.ctx)
            env["USE_SDL3"] = "1"
            env["KIVY_SPLIT_EXAMPLES"] = "1"
            env["KIVY_SDL3_PATH"] = ":".join(
                [
                    *sdl3_mixer_recipe.get_include_dirs(arch),
                    *sdl3_image_recipe.get_include_dirs(arch),
                    *sdl3_ttf_recipe.get_include_dirs(arch),
                    *sdl3_recipe.get_include_dirs(arch),
                ]
            )

        return env


recipe = KivyRecipe()
