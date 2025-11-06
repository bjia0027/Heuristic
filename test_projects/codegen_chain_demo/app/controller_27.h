#pragma once
#include "service_27.h"
#include "model_27.h"
#include <memory>

class Controller27 {
public:
    Controller27();
    void initialize();
    void run();
private:
    std::unique_ptr<Service27> service_;
    std::shared_ptr<Model27> model_;
};
