#pragma once
#include <functional>
#include <vector>

class Service14 {
public:
    Service14();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
