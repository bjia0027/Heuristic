#pragma once
#include "service_24.h"
#include "model_24.h"
#include <memory>

class Controller24 {
public:
    Controller24();
    void initialize();
    void run();
private:
    std::unique_ptr<Service24> service_;
    std::shared_ptr<Model24> model_;
};
