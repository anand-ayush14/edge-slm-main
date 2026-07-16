#!/usr/bin/env python3

from conan import ConanFile
from conan.tools.cmake import CMakeToolchain, CMake, cmake_layout, CMakeDeps
from conan.tools.scm import Git
from conan.tools.files import get, replace_in_file
import os

class FaissConan(ConanFile):
    name = "faiss"
    package_type = "library"
    version = "1.7.4"
    settings = "os", "compiler", "build_type", "arch"
    options = {"shared": [True, False], "fPIC": [True, False]}
    default_options = {"shared": False, "fPIC": True}

    def source(self):
        get(self,
            **self.conan_data["sources"][self.version],
            strip_root=True,
            destination=self.source_folder
        )

    def layout(self):
        cmake_layout(self)

    def requirements(self):
        self.requires("openblas/0.3.26")

    def generate(self):
        deps = CMakeDeps(self)
        deps.generate()
        tc = CMakeToolchain(self)
        if self.settings.os == "Macos":
            # Point Apple Clang to Homebrew's keg-only libomp
            libomp_prefix = "/opt/homebrew/opt/libomp"
            tc.cache_variables["OpenMP_CXX_FLAGS"] = f"-Xpreprocessor -fopenmp -I{libomp_prefix}/include"
            tc.cache_variables["OpenMP_CXX_LIB_NAMES"] = "omp"
            tc.cache_variables["OpenMP_omp_LIBRARY"] = f"{libomp_prefix}/lib/libomp.dylib"
            tc.cache_variables["OpenMP_C_FLAGS"] = f"-Xpreprocessor -fopenmp -I{libomp_prefix}/include"
            tc.cache_variables["OpenMP_C_LIB_NAMES"] = "omp"
        tc.generate()

    def build(self):
        # Make OpenMP non-fatal on platforms where it's not natively available
        replace_in_file(self,
            os.path.join(self.source_folder, "faiss", "CMakeLists.txt"),
            "find_package(OpenMP REQUIRED)",
            "find_package(OpenMP)"
        )
        cmake = CMake(self)
        cmake.configure(variables={
            "FAISS_ENABLE_GPU": "OFF",
            "FAISS_ENABLE_PYTHON": "OFF",
            "FAISS_ENABLE_RAFT": "OFF",
            "FAISS_ENABLE_C_API": "ON",
            "BUILD_TESTING": "OFF",
        })
        cmake.build()

    def package(self):
        cmake = CMake(self)
        cmake.install()

    def package_info(self):
        self.cpp_info.libs = ["faiss"]
